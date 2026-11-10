"""ARINC 429 RX Test IP aracı – tkinter arayüzü."""
from __future__ import annotations

import copy
import dataclasses
import datetime
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from tkinter import font as tkfont

import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk

from . import project as P
from .model import ConfigInputs, SpecProfile, compute, HB_ARINC, HB_50
from .formulas import DERIVED_ROWS, draw_formula
from .txcfg import compute_tx
from .celltable import CellTable, Cell
from .protocol import LinkSettings, Link, LinkError, SIM_PORT, hx, native_port
from .regmap import norm_addr
from .decode import (session_mhz, DecodeSettings, Limits, decode_words, decode_bits, decode_errors, stats, ft,
                     bits_by_word, export_txt, import_txt, ERR_NAMES, UNITS)
from .charts import draw_examples, draw_single, draw_word, relayout

APP = "ARINC 429 Test Aracı"
TIME_UNITS = ["clk", "ns", "µs", "ms"]
GF_RATIO, GF_CLOCK = "Süreye oranlı", "Clock sayısı"
FPGA_NOTES = ["JEDEC JESD8C / Xilinx 7-serisi, UltraScale", "JEDEC / Xilinx: giriş eşikleri LVCMOS33 ile aynı",
              "Kullandığınız FPGA'nın datasheet'i (ör. bazı Intel/Lattice FPGA'larda VIH 1.7 V)"]
# ARINC profil tablosu (OVIEW429 s. 12 düzeni): (grup, [(alan | None: hesaplanan, sütun başlığı)])
ARINC_COLS = [("Bit Rate (kbps)", [("rate_min", "MIN"), ("rate_nom", "NOM"), ("rate_max", "MAX")]),
              ("1 Bit Time", [(None, "µs"), ("bit_tol", "±%")]),
              ("½ Bit Time", [(None, "µs"), ("half_tol", "±%")]),
              ("Rise Time (µs)", [("rise_nom", "NOM"), ("rise_tol", "±")]),
              ("Fall Time (µs)", [("fall_nom", "NOM"), ("fall_tol", "±")]),
              ("Receiver genliği (V)", [("amp_min", "MIN"), ("amp_max", "MAX")]),
              ("k", [("k", "%10–%90")])]
ARINC_PERCENT = ("bit_tol", "half_tol")
FIELD_NAMES = {"clk_mhz": "System Clock", "ppm": "System Clock toleransı", "err": "Test toleransı", "gf_ratio": "Glitch Filter oranı",
               "gf_clock": "Glitch Filter clock sayısı", "pulse_glitch_pct": "Pulse içinde MAX Glitch", "null_glitch_pct": "Null içinde MAX Glitch",
               "gap_glitch_pct": "Word Gap içinde MAX Glitch", "v_one": "One/Zero eşiği", "v_null": "Null eşiği", "tplh": "tPLH", "tphl": "tPHL",
               "trr": "Output Transition trr", "tfr": "Output Transition tfr", "vcc": "VCC", "voh_min": "VOH MIN", "vol_max": "VOL MAX",
               "baud": "Baud", "bytesize": "Data Bits", "stopbits": "Stop Bits", "timeout_ms": "Handshake cevap süresi", "retry": "Deneme sayısı",
               "ack_wait_ms": "Yazma sonrası bekleme", "read_wait_ms": "Okuma cevap süresi"}


def _to_float(text, key):
    try:
        return float(str(text).replace(",", "."))
    except ValueError:
        raise ValueError(f"'{FIELD_NAMES.get(key, key)}' alanı sayı olmalı (girilen: {text!r}).") from None


READ_MODES = {"Tümü": "all", "Son N kayıt": "last", "Okunmasın": "none"}

# Mac ve Windows'ta aynı görünüm için ortak tema ve yazı tipleri
UI_THEME = "clam"
UI_FAMILY = "Arial"
MONO_FAMILY = "Courier New"
UI_SIZE = 12 if sys.platform == "darwin" else 9      # Mac'te 1 punto = 1 piksel, Windows'ta 96 dpi
BOLD_FONT = (UI_FAMILY, UI_SIZE, "bold")
MONO_FONT = (MONO_FAMILY, UI_SIZE)
DEFAULT_OUT_DIR = os.path.join(os.path.expanduser("~"), "ARINC429_okumalar")


def native_dir(path):
    """Başka işletim sisteminde kaydedilmiş klasör yolunu varsayılana çevirir."""
    if os.name == "nt":
        ok = bool(os.path.splitdrive(path)[0])
    else:
        ok = path.startswith("/") and "\\" not in path
    return path if ok else DEFAULT_OUT_DIR


def list_ports():
    try:
        from serial.tools import list_ports as lp
        return [p.device for p in lp.comports()]
    except Exception:
        return []


class _Toolbar(NavigationToolbar2Tk):
    def __init__(self, canvas, window, panel):
        self._panel = panel
        super().__init__(canvas, window, pack_toolbar=False)

    def home(self, *args):
        self._panel.reset()


class FigPanel(ttk.Frame):
    """matplotlib figürü + fare ile yakınlaştırma.
    Tekerlek / iki parmak: imleç etrafında resim gibi iki eksende zoom · Ctrl+tekerlek: yalnız dikey · Shift+tekerlek: yatay kaydırma
    Sol tık sürükle: iki eksende kaydır · Çift tık / Ev butonu: başlangıç görünümü. Araç çubuğundaki büyüteç ile alan seçerek de zoom yapılır."""

    HELP = "Tekerlek / iki parmak: yakınlaştır · Ctrl+Tekerlek: yalnız dikey · Sürükle: kaydır · Çift tık: görünümü sıfırla"
    ZOOM_STEP = 1.08 if sys.platform == "darwin" else 1.3

    def __init__(self, master, figsize=(12, 6)):
        super().__init__(master)
        self.fig = Figure(figsize=figsize, dpi=90)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        bar = ttk.Frame(self); bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.tb = _Toolbar(self.canvas, bar, self)
        self.tb.update(); self.tb.pack(side=tk.LEFT)
        ttk.Label(bar, text=self.HELP, foreground="gray").pack(side=tk.LEFT, padx=8)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._drag = None
        c = self.canvas
        c.mpl_connect("scroll_event", self._on_scroll)
        c.mpl_connect("button_press_event", self._on_press)
        c.mpl_connect("button_release_event", lambda e: setattr(self, "_drag", None))
        c.mpl_connect("motion_notify_event", self._on_move)
        c.mpl_connect("resize_event", lambda e: (relayout(self.fig), self.canvas.draw_idle()))

    def draw(self):
        relayout(self.fig)
        self.canvas.draw_idle()

    def reset(self):
        for ax, (xl, yl) in getattr(self.fig, "_home", {}).items():
            ax.set_xlim(xl); ax.set_ylim(yl)
        self.draw()

    @staticmethod
    def _key(ev, name):
        k = (ev.key or "").lower()
        return name in k

    def _on_scroll(self, ev):
        ax = ev.inaxes
        if ax is None or ev.xdata is None:
            return
        f = 1 / self.ZOOM_STEP if ev.button == "up" else self.ZOOM_STEP
        if self._key(ev, "shift"):                                   # yatay kaydırma
            x0, x1 = ax.get_xlim(); d = (x1 - x0) * 0.15 * (-1 if ev.button == "up" else 1)
            ax.set_xlim(x0 + d, x1 + d)
        elif self._key(ev, "control") or self._key(ev, "ctrl"):      # dikey zoom
            y0, y1 = ax.get_ylim(); y = ev.ydata
            ax.set_ylim(y - (y - y0) * f, y + (y1 - y) * f)
        else:                                                        # resim gibi: iki eksende zoom
            x0, x1 = ax.get_xlim(); x = ev.xdata
            y0, y1 = ax.get_ylim(); y = ev.ydata
            ax.set_xlim(x - (x - x0) * f, x + (x1 - x) * f)
            ax.set_ylim(y - (y - y0) * f, y + (y1 - y) * f)
        self.draw()

    def _on_press(self, ev):
        if ev.inaxes is None or self.tb.mode:
            return
        if ev.dblclick:
            self.reset(); return
        if ev.button == 1:
            self._drag = (ev.inaxes, ev.x, ev.y, ev.inaxes.get_xlim(), ev.inaxes.get_ylim())

    def _on_move(self, ev):
        if not self._drag or self.tb.mode:
            return
        ax, px0, py0, (x0, x1), (y0, y1) = self._drag
        dx = (ev.x - px0) / (ax.bbox.width or 1) * (x1 - x0)
        dy = (ev.y - py0) / (ax.bbox.height or 1) * (y1 - y0)
        ax.set_xlim(x0 - dx, x1 - dx)
        ax.set_ylim(y0 - dy, y1 - dy)
        self.draw()


class ChartWindow(tk.Toplevel):
    """Tek bir RX Config grafiğini ayrı pencerede gösterir."""

    def __init__(self, app, kind, case):
        super().__init__(app)
        self.app, self.kind, self.case = app, kind, case
        self.title(f"RX {'Örnek dalga formu' if kind == 'example' else 'Tek Bit analizi'} – {case}")
        self.geometry("1200x640")
        bar = ttk.Frame(self); bar.pack(fill=tk.X)
        ttk.Label(bar, text="Birim:").pack(side=tk.LEFT, padx=4)
        self.unit = tk.StringVar(value="clk")
        ttk.Combobox(bar, textvariable=self.unit, values=TIME_UNITS, width=6, state="readonly").pack(side=tk.LEFT)
        self.unit.trace_add("write", lambda *a: self.draw())
        self.pattern = tk.StringVar(value="10110010")
        if kind == "example":
            ttk.Label(bar, text="Bit deseni (1/0):").pack(side=tk.LEFT, padx=(12, 4))
            ttk.Entry(bar, textvariable=self.pattern, width=16).pack(side=tk.LEFT)
            self.pattern.trace_add("write", lambda *a: self.draw())
        self.panel = FigPanel(self, (12, 6)); self.panel.pack(fill=tk.BOTH, expand=True)
        self.draw()

    def draw(self):
        app = self.app
        if not app.res:
            return
        try:
            if self.kind == "example":
                pat = [1 if c == "1" else 0 for c in self.pattern.get() if c in "01"] or [1, 0]
                draw_examples(self.panel.fig, app.res, app.ci.clk_mhz, self.unit.get(), pat[:16], only=self.case)
            else:
                draw_single(self.panel.fig, app.res, app.ci.clk_mhz, self.unit.get(), self.case)
            self.panel.draw()
        except Exception as e:
            app.status.set(f"Grafik hatası: {e}")


def make_tree(master, cols, widths=None, height=12):
    fr = ttk.Frame(master)
    tv = ttk.Treeview(fr, columns=cols, show="headings", height=height)
    for i, c in enumerate(cols):
        tv.heading(c, text=c)
        tv.column(c, width=(widths[i] if widths else 100), anchor=tk.CENTER, stretch=False)
    vs = ttk.Scrollbar(fr, orient=tk.VERTICAL, command=tv.yview)
    hs = ttk.Scrollbar(fr, orient=tk.HORIZONTAL, command=tv.xview)
    tv.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
    tv.grid(row=0, column=0, sticky="nsew"); vs.grid(row=0, column=1, sticky="ns"); hs.grid(row=1, column=0, sticky="ew")
    fr.rowconfigure(0, weight=1); fr.columnconfigure(0, weight=1)
    tv.tag_configure("fail", background="#FFC7CE", foreground="#9C0006")
    tv.tag_configure("ok", foreground="#006100")
    tv.tag_configure("sec", background="#DDEBF7", font=BOLD_FONT)
    return fr, tv


def fill_tree(tv, rows, tags=None):
    tv.delete(*tv.get_children())
    for i, r in enumerate(rows):
        tv.insert("", tk.END, values=r, tags=(tags[i],) if tags and tags[i] else ())


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.is_mac = self.tk.call("tk", "windowingsystem") == "aqua"
        self._apply_common_look()
        self.geometry("1500x900")
        self.minsize(1100, 700)
        self.ci, self.ls, self.ds = ConfigInputs(), LinkSettings(), DecodeSettings()
        self.ls.out_dir = DEFAULT_OUT_DIR
        self.sessions: list[dict] = []
        self.cur_session = None
        self.project_path = None
        self.dirty = False
        self.res = None
        self.link: Link | None = None
        self.busy = False
        self._job_cb, self.write_log, self.write_log_path = None, [], None
        self.q = queue.Queue()
        self._recalc_job = None
        self._build_menu()
        nb = ttk.Notebook(self); nb.pack(fill=tk.BOTH, expand=True)
        self.nb = nb
        self._tab_config(nb)
        self._tab_link(nb)
        self._tab_read(nb)
        self._tab_tx_sent(nb)
        self.status = tk.StringVar(value="Hazır.")
        ttk.Label(self, textvariable=self.status, anchor="w", relief=tk.SUNKEN).pack(fill=tk.X, side=tk.BOTTOM)
        self.load_to_form()
        self.recalc()
        self._update_title()
        self.after(50, self._poll)
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _apply_common_look(self):
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont", "TkCaptionFont",
                     "TkSmallCaptionFont", "TkIconFont", "TkTooltipFont"):
            tkfont.nametofont(name).configure(family=UI_FAMILY, size=UI_SIZE, weight="normal")
        tkfont.nametofont("TkFixedFont").configure(family=MONO_FAMILY, size=UI_SIZE)
        style = ttk.Style(self)
        style.theme_use(UI_THEME)
        style.configure("Treeview", rowheight=20)
        style.configure("Bad.TEntry", fieldbackground="#FFC7CE", foreground="#9C0006")
        bg = style.lookup("TFrame", "background")
        self.configure(background=bg)
        self.option_add("*Toplevel.background", bg)
        self.option_add("*TCombobox*Listbox.background", "white")
        self.option_add("*TCombobox*Listbox.foreground", "black")

    # =============================================================== menü / dosya
    def _build_menu(self):
        mod, accel = ("Command", "Command-") if self.is_mac else ("Control", "Ctrl+")
        m = tk.Menu(self)
        f = tk.Menu(m, tearoff=0)
        f.add_command(label="Yeni proje", command=self.new_project)
        f.add_command(label="Proje aç… (.a429proj)", command=self.open_project, accelerator=accel + "O")
        f.add_command(label="Proje kaydet", command=self.save_project, accelerator=accel + "S")
        f.add_command(label="Projeyi farklı kaydet…", command=lambda: self.save_project(True))
        f.add_separator()
        f.add_command(label="RX Config dosyası aç… (.a429cfg)", command=self.open_cfg)
        f.add_command(label="RX Config dosyasını kaydet… (.a429cfg)", command=self.save_cfg)
        f.add_separator()
        f.add_command(label="RX okuma dosyası aç… (.a429read)", command=self.open_read)
        f.add_command(label="Seçili RX okumasını kaydet… (.a429read)", command=self.save_read)
        f.add_command(label="TTL/Excel txt dosyalarından içe aktar…", command=self.import_ttl)
        f.add_command(label="Seçili RX okumasını TTL/Excel txt olarak dışa aktar…", command=self.export_ttl)
        f.add_separator()
        f.add_command(label="Çıkış", command=self.on_close)
        m.add_cascade(label="Dosya", menu=f)
        a = tk.Menu(m, tearoff=0)
        a.add_command(label="Komut ve Register Düzenleyici…", command=self.open_reg_editor)
        m.add_cascade(label="Ayarlar", menu=a)
        h = tk.Menu(m, tearoff=0)
        h.add_command(label="Hakkında", command=lambda: messagebox.showinfo(APP, (
            "ARINC 429 RX/TX test aracı\n\nRX Config hesaplama, seri port ile RX Config gönderme ve RX veri okuma, "
            "okunan RX verilerinin çözümlenmesi ve dalga formu görüntüleme.\n\n"
            "Port listesinden 'SIMÜLATÖR' seçilirse program kart olmadan denenebilir.")))
        m.add_cascade(label="Yardım", menu=h)
        self.config(menu=m)
        self.bind_all(f"<{mod}-s>", lambda e: self.save_project())
        self.bind_all(f"<{mod}-o>", lambda e: self.open_project())

    def _update_title(self):
        name = os.path.basename(self.project_path) if self.project_path else "Yeni proje"
        self.title(f"{APP} – {name}{' *' if self.dirty else ''}")

    def mark_dirty(self):
        if not self.dirty:
            self.dirty = True; self._update_title()

    def _confirm_discard(self):
        if not self.dirty:
            return True
        r = messagebox.askyesnocancel(APP, "Kaydedilmemiş değişiklikler var. Projeyi kaydedeyim mi?")
        if r is None:
            return False
        if r:
            return self.save_project()
        return True

    def new_project(self):
        if not self._confirm_discard():
            return
        out = self.ls.out_dir
        self.ci, self.ls, self.ds = ConfigInputs(), LinkSettings(), DecodeSettings()
        self.ls.out_dir = out
        self.sessions, self.cur_session, self.project_path, self.dirty = [], None, None, False
        self.load_to_form(); self.recalc(); self.refresh_sessions(); self._update_title()

    def open_project(self):
        if not self._confirm_discard():
            return
        p = filedialog.askopenfilename(filetypes=[("ARINC429 proje", "*.a429proj"), ("Tümü", "*.*")])
        if not p:
            return
        try:
            self.ci, self.ls, self.ds, self.sessions = P.load_project(p)
        except Exception as e:
            messagebox.showerror(APP, f"Proje açılamadı:\n{e}"); return
        self.project_path, self.dirty = p, False
        self.cur_session = self.sessions[-1] if self.sessions else None
        self.load_to_form(); self.recalc(); self.refresh_sessions(); self._update_title()
        self.status.set(f"Proje açıldı: {p} ({len(self.sessions)} okuma)")

    def save_project(self, ask=False):
        if not self._commit_form():
            return False
        p = self.project_path
        if ask or not p:
            p = filedialog.asksaveasfilename(defaultextension=".a429proj", filetypes=[("ARINC429 proje", "*.a429proj")])
            if not p:
                return False
        try:
            P.save_project(p, self.ci, self.ls, self.ds, self.sessions)
        except Exception as e:
            messagebox.showerror(APP, f"Kaydedilemedi:\n{e}"); return False
        self.project_path, self.dirty = p, False
        self._update_title(); self.status.set(f"Proje kaydedildi: {p}")
        return True

    def open_cfg(self):
        p = filedialog.askopenfilename(filetypes=[("ARINC429 config", "*.a429cfg"), ("Tümü", "*.*")])
        if not p:
            return
        try:
            self.ci, ls, self.ds = P.load_config(p)
        except Exception as e:
            messagebox.showerror(APP, f"RX Config açılamadı:\n{e}"); return
        out = self.ls.out_dir; self.ls = ls; self.ls.out_dir = ls.out_dir or out
        self.load_to_form(); self.recalc(); self.mark_dirty()
        self.status.set(f"RX Config yüklendi: {p}")

    def save_cfg(self):
        if not self._commit_form():
            return
        p = filedialog.asksaveasfilename(defaultextension=".a429cfg", filetypes=[("ARINC429 config", "*.a429cfg")])
        if p:
            P.save_config(p, self.ci, self.ls, self.ds); self.status.set(f"RX Config kaydedildi: {p}")

    def open_read(self):
        ps = filedialog.askopenfilenames(filetypes=[("ARINC429 okuma", "*.a429read"), ("Tümü", "*.*")])
        for p in ps:
            try:
                s = P.load_session(p)
            except Exception as e:
                messagebox.showerror(APP, f"{p} açılamadı:\n{e}"); continue
            self.add_session(s, save_file=False)

    def save_read(self):
        if not self.cur_session:
            return
        p = filedialog.asksaveasfilename(defaultextension=".a429read", initialfile=self.cur_session["name"],
                                         filetypes=[("ARINC429 okuma", "*.a429read")])
        if p:
            P.save_session(p, self.cur_session); self.status.set(f"Okuma kaydedildi: {p}")

    def import_ttl(self):
        d = filedialog.askdirectory(title="a429_words.txt vb. dosyaların olduğu klasör")
        if not d:
            return
        rd = lambda n: open(os.path.join(d, n), encoding="utf-8", errors="ignore").read() if os.path.exists(os.path.join(d, n)) else ""
        s = import_txt(rd("a429_words.txt"), rd("a429_errors.txt"), rd("a429_bits.txt"), rd("a429_summary.txt"))
        s = P.new_session(s, self.ci, self.ls, self.ds, name="ttl_" + os.path.basename(d.rstrip("/\\")))
        self.add_session(s, save_file=False)

    def export_ttl(self):
        if not self.cur_session:
            return
        d = filedialog.askdirectory(title="Dışa aktarılacak klasör")
        if not d:
            return
        for fn, txt in export_txt(self.cur_session).items():
            with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
                f.write(txt + "\n")
        self.status.set(f"TTL/Excel txt dosyaları yazıldı: {d}")

    def on_close(self):
        if self.busy and not messagebox.askyesno(APP, "Seri port işlemi sürüyor. Yine de çıkılsın mı?"):
            return
        if not self._confirm_discard():
            return
        if self.link:
            self.link.stop_flag.set(); self.link.close()
        self.destroy()

    # =============================================================== sekme: Config
    def _tab_config(self, nb):
        t = ttk.Frame(nb); nb.add(t, text="Config")
        left = ttk.Frame(t); left.pack(side=tk.LEFT, fill=tk.Y, padx=(6, 0), pady=6)
        right = ttk.Frame(t); right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.v, self.chart_wins = {}, {}
        self._build_config_inputs(left)
        self._build_config_results(right)

    def _num_var(self):
        var = tk.StringVar(); var.trace_add("write", lambda *a: self.schedule_recalc())
        return var

    def _profile_combo(self, parent, key, width=24):
        cb = ttk.Combobox(parent, textvariable=self.v[key], width=width, state="readonly")
        cb.bind("<<ComboboxSelected>>", lambda e: self._select_profile(key))
        self.profile_combos[key].append(cb)
        return cb

    def _refresh_profile_combos(self):
        for key, combos in self.profile_combos.items():
            combos[:] = [c for c in combos if c.winfo_exists()]
            for c in combos:
                c.configure(values=[p.name for p in self._profiles(key)])

    def _profile_bar(self, parent, key):
        """Düzenleme penceresi için profil seçimi: combobox + Yeni / Adlandır / Sil."""
        bar = ttk.Frame(parent); bar.pack(fill=tk.X, pady=(0, 6))
        self._profile_combo(bar, key).pack(side=tk.LEFT, padx=(0, 4))
        for txt, fn in (("Yeni", self._new_profile), ("Adlandır", self._rename_profile), ("Sil", self._del_profile)):
            ttk.Button(bar, text=txt, width=len(txt) + 1, command=lambda f=fn: f(key)).pack(side=tk.LEFT, padx=1)
        self._refresh_profile_combos()

    def _build_config_inputs(self, left):
        self.pv = {k: self._num_var() for k in ("rate_min", "rate_nom", "rate_max", "rate_tol", "bit_tol", "half_tol", "rise_nom",
                                                "rise_tol", "fall_nom", "fall_tol", "amp_min", "amp_max", "k")}
        self.icv = {k: [self._num_var() for _ in range(3)] for k in ("v_one", "v_null", "tplh", "tphl", "trr", "tfr", "vcc")}
        self.icx = {"voh_min": self._num_var(), "vol_max": self._num_var()}
        self.fpv = [[self._num_var() for _ in range(3)] for _ in range(3)]
        for k in ("half_ref", "fpga_std", "clk_mhz", "ppm", "err", "gf_mode", "gf_ratio", "gf_ref", "gf_clock",
                  "pulse_glitch_pct", "null_glitch_pct", "gap_glitch_pct", "glitch_base"):
            self.v[k] = self._num_var()
        self.v["profile"], self.v["tx_profile"], self.v["ic_profile"] = tk.StringVar(), tk.StringVar(), tk.StringVar()
        self.v["gf_mode"].trace_add("write", lambda *a: self._show_gf_inputs())
        self.profile_combos = {"profile": [], "tx_profile": [], "ic_profile": []}
        self.settings_wins, self.summary = {}, {}
        self.gf_ratio_widgets, self.gf_clock_widgets = (), ()

        def panel(title):
            g = ttk.LabelFrame(left, text=title); g.pack(fill=tk.X, pady=(0, 8))
            return g

        def label(g, r, text):
            ttk.Label(g, text=text).grid(row=r, column=0, sticky="w", padx=(6, 10), pady=3)

        g = panel("Genel")
        for r, (key, text) in enumerate((("clk_mhz", "System Clock (MHz)"), ("ppm", "System Clock toleransı (±ppm)"))):
            label(g, r, text)
            ttk.Entry(g, textvariable=self.v[key], width=10).grid(row=r, column=1, sticky="w")
        ttk.Button(g, text="Komut ve Register'ları düzenle…", command=self.open_reg_editor).grid(
            row=2, column=0, columnspan=3, sticky="ew", padx=6, pady=3)

        g = panel("RX Config")
        label(g, 0, "ARINC 429 profili"); self._profile_combo(g, "profile", 22).grid(row=0, column=1, sticky="w")
        ttk.Button(g, text="Düzenle…", command=self._open_arinc).grid(row=0, column=2, padx=6)
        label(g, 1, "Receiver entegresi"); self._profile_combo(g, "ic_profile", 22).grid(row=1, column=1, sticky="w")
        ttk.Button(g, text="Düzenle…", command=self._open_ic).grid(row=1, column=2, padx=6)
        label(g, 2, "FPGA giriş standardı")
        self.cb_fpga = ttk.Combobox(g, textvariable=self.v["fpga_std"], width=22, state="readonly")
        self.cb_fpga.grid(row=2, column=1, sticky="w")
        ttk.Button(g, text="Düzenle…", command=self._open_fpga).grid(row=2, column=2, padx=6)
        label(g, 3, "Glitch Filter ve limitler")
        ttk.Button(g, text="Düzenle…", command=self._open_glitch).grid(row=3, column=2, padx=6)
        self.summary["glitch"] = ttk.Label(g, text="", foreground="gray", wraplength=240, justify=tk.LEFT)
        self.summary["glitch"].grid(row=3, column=1, sticky="w")
        label(g, 4, "Test toleransı (%)")
        ttk.Entry(g, textvariable=self.v["err"], width=10).grid(row=4, column=1, sticky="w")
        for r, (kind, text) in enumerate((("example", "Örnek dalga formu"), ("single", "Tek Bit analizi")), 5):
            label(g, r, text)
            f = ttk.Frame(g); f.grid(row=r, column=1, columnspan=2, sticky="w")
            for case in ("MIN", "NOM", "MAX"):
                ttk.Button(f, text=case, width=5, command=lambda k=kind, c=case: self.open_chart(k, c)).pack(side=tk.LEFT, padx=1)

        g = panel("TX Config")
        label(g, 0, "ARINC 429 profili"); self._profile_combo(g, "tx_profile", 22).grid(row=0, column=1, sticky="w")
        ttk.Button(g, text="Düzenle…", command=self._open_arinc).grid(row=0, column=2, padx=6)

    # ------------------------------------------------------------ ayar pencereleri
    def _settings_window(self, key, title, build):
        win = self.settings_wins.get(key)
        if win is not None and win.winfo_exists():
            win.lift(); win.focus_set(); return win
        win = tk.Toplevel(self); win.title(title); win.transient(self); win.resizable(False, False)
        win.configure(background=ttk.Style(self).lookup("TFrame", "background"))
        body = ttk.Frame(win, padding=10); body.pack(fill=tk.BOTH, expand=True)
        build(body)
        ttk.Label(body, text="Değişiklikler sonuçlara anında yansır.", foreground="gray").pack(anchor="w", pady=(8, 0))
        ttk.Button(body, text="Kapat", command=lambda: self._close_settings(win)).pack(anchor="e", pady=(4, 0))
        win.protocol("WM_DELETE_WINDOW", lambda: self._close_settings(win))
        win.bind("<Escape>", lambda e: self._close_settings(win))
        self.settings_wins[key] = win
        return win

    def _close_settings(self, win):
        check = getattr(win, "validate", None)
        if check and not check():
            return
        if self._commit_form():
            win.destroy()

    @staticmethod
    def _grid_label(fr, r, text):
        ttk.Label(fr, text=text).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=2)

    @staticmethod
    def _grid_entry(fr, r, c, var, width=9):
        ttk.Entry(fr, textvariable=var, width=width).grid(row=r, column=c, padx=2, pady=2)

    @staticmethod
    def _grid_header(fr, names=("MIN", "NOM", "MAX")):
        for j, h in enumerate(names):
            ttk.Label(fr, text=h, font=BOLD_FONT).grid(row=0, column=j + 1)

    def _open_arinc(self):
        def build(body):
            self.arinc_grid = grid = ttk.Frame(body); grid.pack(fill=tk.X)
            for c, text in enumerate(("RX", "TX", "Profil")):
                ttk.Label(grid, text=text, font=BOLD_FONT, anchor="center", relief=tk.GROOVE).grid(
                    row=0, column=c, rowspan=2, sticky="nsew", padx=1, pady=1)
            c = 3
            for group, cols in ARINC_COLS:
                ttk.Label(grid, text=group, font=BOLD_FONT, anchor="center", relief=tk.GROOVE).grid(
                    row=0, column=c, columnspan=len(cols), sticky="ew", padx=1, pady=1)
                for field_, head in cols:
                    ttk.Label(grid, text=head, anchor="center").grid(row=1, column=c, sticky="ew", padx=1)
                    c += 1
            ttk.Label(grid, text="İşlem", font=BOLD_FONT, anchor="center", relief=tk.GROOVE).grid(
                row=0, column=c, rowspan=2, sticky="nsew", padx=1, pady=1)
            self._fill_arinc_rows()
            bar = ttk.Frame(body); bar.pack(fill=tk.X, pady=(6, 0))
            ttk.Label(bar, text="½ Bit Time ölçüm referansı").pack(side=tk.LEFT, padx=(0, 6))
            ttk.Combobox(bar, textvariable=self.v["half_ref"], values=[HB_ARINC, HB_50], width=28, state="readonly").pack(side=tk.LEFT)
            ttk.Label(body, text="RX ve TX aynı profil listesini kullanır; RX ve TX sütunlarından her biri ayrı profile ayarlanabilir. "
                                 "Kaynak: ARINC 429 Tutorial (OVIEW429, s. 11-12). k, Rise/Fall ölçümünün %10–%90 aralığıdır. "
                                 "1 Bit Time ve ½ Bit Time µs değerleri Bit Rate NOM'dan hesaplanır. Dokümandaki Bit Rate ±%1, Bit Time toleransının içinde kalır.",
                      foreground="gray", wraplength=1050, justify=tk.LEFT).pack(anchor="w", pady=(6, 0))
        win = self._settings_window("arinc", "ARINC 429 profilleri (RX ve TX ortak)", build)
        win.validate = self._arinc_valid

    def _arinc_valid(self):
        if self.arinc_bad:
            messagebox.showerror(APP, "Tabloda geçersiz değer var (kırmızı hücreler)."); return False
        return True

    def _fill_arinc_rows(self):
        grid = getattr(self, "arinc_grid", None)
        self.arinc_bad = set()
        if grid is None or not grid.winfo_exists():
            return
        for w in grid.grid_slaves():
            if int(w.grid_info()["row"]) >= 2:
                w.destroy()
        for r, prof in enumerate(self.ci.profiles, 2):
            for c, key in enumerate(("profile", "tx_profile")):
                ttk.Radiobutton(grid, variable=self.v[key], value=prof.name,
                                command=lambda k=key: self._select_profile(k)).grid(row=r, column=c, padx=4, pady=2)
            ttk.Label(grid, text=prof.name).grid(row=r, column=2, sticky="w", padx=4)
            calc, c = [], 3
            for _, cols in ARINC_COLS:
                for field_, _head in cols:
                    if field_ is None:
                        lbl = ttk.Label(grid, width=7, anchor="center", foreground="#404040")
                        lbl.grid(row=r, column=c, padx=1); calc.append(lbl)
                    else:
                        value = getattr(prof, field_) * (100 if field_ in ARINC_PERCENT else 1)
                        var = tk.StringVar(value=f"{value:g}")
                        e = ttk.Entry(grid, textvariable=var, width=7, justify=tk.CENTER)
                        e.grid(row=r, column=c, padx=1, pady=2)
                        var.trace_add("write", lambda *a, p=prof, f=field_, v=var, w=e, l=calc: self._arinc_edit(p, f, v, w, l))
                    c += 1
            self._arinc_calc(prof, calc)
            ops = ttk.Frame(grid); ops.grid(row=r, column=c, padx=2)
            for txt, fn in (("Kopyala", self._new_profile), ("Adlandır", self._rename_profile), ("Sil", self._del_profile)):
                ttk.Button(ops, text=txt, width=len(txt) + 1, command=lambda f=fn, x=prof: f("profile", x)).pack(side=tk.LEFT, padx=1)

    @staticmethod
    def _arinc_calc(prof, labels):
        ok = prof.rate_nom > 0
        labels[0].configure(text=f"{1000 / prof.rate_nom:g}" if ok else "–")
        labels[1].configure(text=f"{500 / prof.rate_nom:g}" if ok else "–")

    def _arinc_edit(self, prof, field_, var, entry, labels):
        try:
            value = float(var.get().replace(",", "."))
        except ValueError:
            entry.configure(style="Bad.TEntry"); self.arinc_bad.add(entry)
            self.status.set("ARINC profil tablosunda geçersiz değer."); return
        entry.configure(style="TEntry"); self.arinc_bad.discard(entry)
        value = value / 100 if field_ in ARINC_PERCENT else value
        setattr(prof, field_, value)
        self._arinc_calc(prof, labels)
        if prof is self.ci.get_profile():
            self.pv[field_].set(f"{value:g}")       # schedule_recalc tetikler
        else:
            self.mark_dirty()

    def _open_ic(self):
        def build(body):
            self._profile_bar(body, "ic_profile")
            f = ttk.Frame(body); f.pack(fill=tk.X)
            self._grid_header(f)
            for r, (k, text) in enumerate((("v_one", "One/Zero eşiği (V)"), ("v_null", "Null eşiği (V)"),
                                           ("tplh", "Propagation Delay tPLH (ns)"), ("tphl", "Propagation Delay tPHL (ns)"),
                                           ("trr", "Output Transition trr (ns)"), ("tfr", "Output Transition tfr (ns)"),
                                           ("vcc", "VCC = çıkış salınımı (V)")), 1):
                self._grid_label(f, r, text)
                for j, var in enumerate(self.icv[k]):
                    self._grid_entry(f, r, j + 1, var)
            self._grid_label(f, 8, "Çıkış VOH MIN / VOL MAX (V)")
            self._grid_entry(f, 8, 1, self.icx["voh_min"]); self._grid_entry(f, 8, 3, self.icx["vol_max"])
            ttk.Label(body, text="Datasheet'te MIN değeri yoksa 0 yazın (en kötü durum).", foreground="gray").pack(anchor="w", pady=(6, 0))
        self._settings_window("ic", "RX Receiver entegresi", build)

    def _open_fpga(self):
        def build(body):
            f = ttk.Frame(body); f.pack(fill=tk.X)
            for j, h in enumerate(("Standart", "VIL MAX (V)", "VIH MIN (V)", "Kaynak")):
                ttk.Label(f, text=h, font=BOLD_FONT).grid(row=0, column=j, padx=4, sticky="w" if j == 3 else "")
            for i, vs in enumerate(self.fpv):
                ttk.Entry(f, textvariable=vs[0], width=14).grid(row=i + 1, column=0, padx=4, pady=2)
                self._grid_entry(f, i + 1, 1, vs[1]); self._grid_entry(f, i + 1, 2, vs[2])
                ttk.Label(f, text=FPGA_NOTES[i], foreground="gray").grid(row=i + 1, column=3, sticky="w", padx=4)
            ttk.Label(body, text="Giriş eşiğinin VIL MAX ile VIH MIN arasında olduğu, Schmitt Trigger bulunmadığı varsayılır.",
                      foreground="gray").pack(anchor="w", pady=(6, 0))
        self._settings_window("fpga", "RX FPGA giriş standartları", build)

    def _open_glitch(self):
        def combo(fr, r, key, values):
            ttk.Combobox(fr, textvariable=self.v[key], values=values, width=18, state="readonly").grid(row=r, column=1, sticky="w", pady=2)

        def pair(fr, r, text, key):
            lbl = ttk.Label(fr, text=text); lbl.grid(row=r, column=0, sticky="w", padx=(0, 10), pady=2)
            w = ttk.Entry(fr, textvariable=self.v[key], width=20); w.grid(row=r, column=1, sticky="w", pady=2)
            return lbl, w

        def build(body):
            g = ttk.LabelFrame(body, text="Glitch Filter", padding=6); g.pack(fill=tk.X)
            self._grid_label(g, 0, "Hesap yöntemi"); combo(g, 0, "gf_mode", [GF_RATIO, GF_CLOCK])
            lbl = ttk.Label(g, text="Oranın referans süresi"); lbl.grid(row=2, column=0, sticky="w", padx=(0, 10), pady=2)
            cb = ttk.Combobox(g, textvariable=self.v["gf_ref"], values=["Min Pulse", "Min Null", "Min Bit"], width=18, state="readonly")
            cb.grid(row=2, column=1, sticky="w", pady=2)
            self.gf_ratio_widgets = pair(g, 1, "Oran (%)", "gf_ratio") + (lbl, cb)
            self.gf_clock_widgets = pair(g, 3, "Clock sayısı", "gf_clock")
            self._show_gf_inputs()
            g = ttk.LabelFrame(body, text="Glitch Error limitleri", padding=6); g.pack(fill=tk.X, pady=(6, 0))
            pair(g, 0, "Pulse içinde MAX Glitch (%)", "pulse_glitch_pct")
            pair(g, 1, "Null içinde MAX Glitch (%)", "null_glitch_pct")
            pair(g, 2, "Word Gap içinde MAX Glitch (%)", "gap_glitch_pct")
            self._grid_label(g, 3, "Pulse/Null referans süresi"); combo(g, 3, "glitch_base", ["MIN", "NOM", "MAX"])
            ttk.Label(g, text="Word Gap referans süresi sabittir: 4 × Min Bit", foreground="gray").grid(row=4, column=0, columnspan=2, sticky="w")
        self._settings_window("glitch", "RX Glitch Filter ve limitler", build)

    def _update_summaries(self, vil, vih):
        ci = self.ci
        gf = f"%{ci.gf_ratio * 100:g} × {ci.gf_ref}" if ci.gf_mode == "ratio" else f"{ci.gf_clock} clock"
        self.summary["glitch"].configure(text=f"Filter: {gf} · Limit Pulse/Null/Gap %{ci.pulse_glitch_pct * 100:g}/{ci.null_glitch_pct * 100:g}/{ci.gap_glitch_pct * 100:g}")

    def _show_gf_inputs(self):
        if not (self.gf_ratio_widgets and self.gf_ratio_widgets[0].winfo_exists()):
            return
        by_clock = self.v["gf_mode"].get() == GF_CLOCK
        for w in self.gf_ratio_widgets:
            w.grid_remove() if by_clock else w.grid()
        for w in self.gf_clock_widgets:
            w.grid() if by_clock else w.grid_remove()

    # ------------------------------------------------------------ adlı profiller
    def _profiles(self, key):
        return self.ci.ic_profiles if key == "ic_profile" else self.ci.profiles

    def _current(self, key):
        items = self._profiles(key)
        return next((p for p in items if p.name == getattr(self.ci, key)), items[0])

    def _commit_form(self):
        try:
            self.form_to_model(); return True
        except ValueError as e:
            messagebox.showerror(APP, f"Önce alanları düzeltin:\n{e}"); return False

    def _activate(self, key, name):
        setattr(self.ci, key, name)
        self.load_to_form(); self._show_gf_inputs(); self.recalc(); self.mark_dirty()

    def _select_profile(self, key):
        if self._commit_form():
            self._activate(key, self.v[key].get())
        else:
            self.v[key].set(self._current(key).name)

    def _ask_name(self, key, title, initial):
        name = simpledialog.askstring(APP, title, parent=self, initialvalue=initial)
        if not name or not name.strip():
            return None
        name = name.strip()
        if any(p.name == name for p in self._profiles(key)):
            messagebox.showerror(APP, f"'{name}' adında bir profil var."); return None
        return name

    def _reload_profiles(self):
        self.load_to_form(); self._show_gf_inputs(); self.recalc(); self.mark_dirty()

    def _new_profile(self, key, target=None):
        if not self._commit_form():
            return
        cur = target or self._current(key)
        name = self._ask_name(key, "Yeni profil adı (seçilen profilin kopyası oluşturulur):", f"{cur.name} kopya")
        if not name:
            return
        self._profiles(key).append(dataclasses.replace(cur, name=name))
        if target is None:
            self._activate(key, name)
        else:
            self._reload_profiles()

    def _rename_profile(self, key, target=None):
        if not self._commit_form():
            return
        cur = target or self._current(key)
        name = self._ask_name(key, "Yeni ad:", cur.name)
        if not name:
            return
        old, cur.name = cur.name, name
        for k in (("ic_profile",) if key == "ic_profile" else ("profile", "tx_profile")):
            if getattr(self.ci, k) == old:
                setattr(self.ci, k, name)
        self._reload_profiles()

    def _del_profile(self, key, target=None):
        items = self._profiles(key)
        if len(items) <= 1:
            messagebox.showinfo(APP, "En az bir profil kalmalı."); return
        if not self._commit_form():
            return
        cur = target or self._current(key)
        if not messagebox.askyesno(APP, f"'{cur.name}' profili silinsin mi?"):
            return
        items.remove(cur)
        for k in (("ic_profile",) if key == "ic_profile" else ("profile", "tx_profile")):
            if getattr(self.ci, k) == cur.name:
                setattr(self.ci, k, items[0].name)
        self._reload_profiles()

    # ------------------------------------------------------------ sonuçlar
    def _build_config_results(self, right):
        side = ttk.Notebook(right); side.pack(fill=tk.BOTH, expand=True); self.side_nb = side
        rx = ttk.Frame(side, padding=4); side.add(rx, text="RX")
        tx = ttk.Frame(side, padding=4); side.add(tx, text="TX")

        self.chk_lbl = ttk.Label(rx, text="", font=BOLD_FONT); self.chk_lbl.pack(fill=tk.X, pady=(0, 4))
        det = ttk.Notebook(rx); det.pack(fill=tk.BOTH, expand=True)
        a = ttk.Frame(det); det.add(a, text="Kontroller")
        fr, self.tv_chk = make_tree(a, ("Kontrol", "Sonuç"), [520, 90], 8); fr.pack(fill=tk.BOTH, expand=True)
        a = ttk.Frame(det); det.add(a, text="Test toleransı eklenmiş süreler")
        fr, self.tv_dur = make_tree(a, ("Parametre", "µs", "clk"), [340, 100, 100], 8); fr.pack(fill=tk.BOTH, expand=True)
        self.tv_dur.bind("<Double-1>", lambda e: self._open_formula(e, self.tv_dur, ("µs", "clk")))
        ttk.Label(a, text="Formülü görmek için satıra çift tıklayın.", foreground="gray").pack(anchor="w", padx=4)
        a = ttk.Frame(det); det.add(a, text="Ara hesaplar ve formüller")
        ttk.Label(a, text="Fiziksel en kötü durum, test toleransı eklenmemiş. MIN: Min Pulse durumu, MAX: Max Pulse durumu. Formülü görmek için satıra çift tıklayın.",
                  foreground="gray").pack(anchor="w", padx=4, pady=2)
        fr, self.tv_mid = make_tree(a, ("Parametre", "MIN", "NOM", "MAX"), [440, 90, 90, 90], 8); fr.pack(fill=tk.BOTH, expand=True)
        self.tv_mid.bind("<Double-1>", lambda e: self._open_formula(e, self.tv_mid, ("MIN", "NOM", "MAX")))

        g = ttk.LabelFrame(rx, text="RX Config Register'ları"); g.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        fr, self.tv_regs = make_tree(g, ("Register", "Register Adresi", "Değer", "Değer (hex)", "Yazma Komutu (hex)"),
                                     [260, 110, 100, 130, 260], 8)
        fr.pack(fill=tk.BOTH, expand=True)
        ttk.Button(g, text="Komutları panoya kopyala", command=self.copy_cmds).pack(anchor="w", padx=2, pady=2)

        self.tx_chk_lbl = ttk.Label(tx, text="", font=BOLD_FONT); self.tx_chk_lbl.pack(fill=tk.X)
        self.tx_info = ttk.Label(tx, text="", foreground="gray"); self.tx_info.pack(fill=tk.X, pady=(0, 4))
        g = ttk.LabelFrame(tx, text="TX Kontrolleri"); g.pack(fill=tk.BOTH, expand=True)
        fr, self.tv_tx_chk = make_tree(g, ("Kontrol", "Sonuç"), [520, 90], 8); fr.pack(fill=tk.BOTH, expand=True)
        g = ttk.LabelFrame(tx, text="TX Config Register'ları"); g.pack(fill=tk.BOTH, expand=True, pady=(6, 0))
        fr, self.tv_tx_regs = make_tree(g, ("Register", "Register Adresi", "Değer", "Değer (hex)", "Yazma Komutu (hex)"),
                                        [260, 110, 100, 130, 260], 8)
        fr.pack(fill=tk.BOTH, expand=True)

    def open_chart(self, kind, case):
        win = self.chart_wins.get((kind, case))
        if win is not None and win.winfo_exists():
            win.lift(); return
        self.chart_wins[(kind, case)] = ChartWindow(self, kind, case)

    def draw_cfg_charts(self):
        for win in list(self.chart_wins.values()):
            if win.winfo_exists():
                win.draw()

    def copy_cmds(self):
        if not self.res:
            return
        self.clipboard_clear()
        self.clipboard_append("\n".join(r[4] for r in self.res.regs if r[2] is not None))
        self.status.set("Yazma komutları panoya kopyalandı.")

    def _open_formula(self, ev, tv, heads):
        item = tv.identify_row(ev.y)
        if not item:
            return
        vals = tv.item(item, "values")
        if "gecikmesi" in vals[0]:          # bu satırlarda MIN/MAX, en küçük/en büyük değil Pulse durumudur
            heads = ("Min Pulse durumu", "NOM", "Max Pulse durumu")
        key, shown = vals[0], " · ".join(f"{h} = {v}" for h, v in zip(heads, vals[1:]) if v != "")
        old = getattr(self, "formula_win", None)
        if old is not None and old.winfo_exists():
            old.destroy()
        top = tk.Toplevel(self); top.title(f"RX Formül – {key}"); top.configure(background="white"); top.transient(self)
        self.formula_win = top
        ttk.Label(top, text=f"Güncel değer:  {shown}", font=BOLD_FONT, background="white").pack(anchor="w", padx=14, pady=(10, 0))
        fig = Figure(dpi=100)
        w, h = draw_formula(fig, key)
        canvas = FigureCanvasTkAgg(fig, master=top)
        canvas.get_tk_widget().configure(width=int(w * 100), height=int(h * 100), highlightthickness=0)
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        canvas.draw()
        top.bind("<Escape>", lambda e: top.destroy())

    def open_reg_editor(self):
        if self.busy:
            messagebox.showinfo(APP, "Seri port işlemi sürerken düzenlenemez."); return
        from .regedit import RegisterEditor
        if not self._commit_form():
            return
        self.reg_editor = RegisterEditor(self)

    # =============================================================== sekme: Bağlantı
    def _tab_link(self, nb):
        t = ttk.Frame(nb); nb.add(t, text="Bağlantı")
        left = ttk.Frame(t); left.pack(side=tk.LEFT, fill=tk.Y, padx=6, pady=6)
        right = ttk.Frame(t); right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=6, pady=6)
        self.lv = {}

        def ent(fr, r, c, label, key, width=8, combo=None):
            ttk.Label(fr, text=label).grid(row=r, column=c, sticky="w", padx=(4, 2), pady=1)
            var = tk.StringVar(); self.lv[key] = var
            w = (ttk.Combobox(fr, textvariable=var, values=combo, width=width) if combo is not None
                 else ttk.Entry(fr, textvariable=var, width=width))
            w.grid(row=r, column=c + 1, sticky="w", pady=1)
            var.trace_add("write", lambda *a: self.mark_dirty())
            return w

        g = ttk.LabelFrame(left, text="Seri port"); g.pack(fill=tk.X, pady=3)
        self.cb_port = ent(g, 0, 0, "Port", "port", 14, [SIM_PORT] + list_ports())
        ttk.Button(g, text="↻", width=3, command=lambda: self.cb_port.configure(values=[SIM_PORT] + list_ports())).grid(row=0, column=2)
        ent(g, 1, 0, "Baud", "baud", 10, ["9600", "19200", "38400", "57600", "115200", "230400", "460800", "921600"])
        ent(g, 2, 0, "Data Bits", "bytesize", 4, ["5", "6", "7", "8"])
        ent(g, 3, 0, "Parity", "parity", 4, ["N", "E", "O", "M", "S"])
        ent(g, 4, 0, "Stop Bits", "stopbits", 4, ["1", "1.5", "2"])
        ttk.Label(g, text="Hedef IP portu (hex)").grid(row=5, column=0, sticky="w", padx=(4, 2), pady=1)
        self.v["ip_port"] = tk.StringVar()
        ttk.Entry(g, textvariable=self.v["ip_port"], width=6).grid(row=5, column=1, sticky="w", pady=1)
        self.v["ip_port"].trace_add("write", lambda *a: self.schedule_recalc())
        g = ttk.LabelFrame(left, text="Handshake ve zamanlama"); g.pack(fill=tk.X, pady=3)
        ent(g, 0, 0, "Handshake dizisi (hex)", "handshake", 44)
        ent(g, 1, 0, "Handshake cevabı (hex)", "hs_response", 44)
        ent(g, 2, 0, "Handshake cevap süresi (ms)", "timeout_ms", 6)
        ent(g, 3, 0, "Deneme sayısı", "retry", 4)
        ent(g, 4, 0, "Yazma sonrası bekleme (ms)", "ack_wait_ms", 6)
        ent(g, 6, 0, "Okuma cevap süresi (ms)", "read_wait_ms", 6)
        g = ttk.LabelFrame(left, text="Komut ve Register'lar"); g.pack(fill=tk.X, pady=3)
        ttk.Label(g, text="Yazma/okuma komut yapısı ve tüm Register adresleri", foreground="gray").pack(anchor="w", padx=4)
        ttk.Button(g, text="Komut ve Register'ları düzenle…", command=self.open_reg_editor).pack(fill=tk.X, padx=4, pady=3)
        g = ttk.LabelFrame(left, text="Okunacak RX verileri"); g.pack(fill=tk.X, pady=3)
        self.read_opts = {}
        for r, (key, lab) in enumerate((("word", "Word"), ("error", "Error"), ("bit", "Bit Diagnostic"))):
            ttk.Label(g, text=lab).grid(row=r, column=0, sticky="w", padx=(4, 8), pady=1)
            mode, n = tk.StringVar(), tk.StringVar()
            ttk.Combobox(g, textvariable=mode, values=list(READ_MODES), width=12, state="readonly").grid(row=r, column=1, sticky="w", pady=1)
            e = ttk.Entry(g, textvariable=n, width=6); e.grid(row=r, column=2, sticky="w", padx=4, pady=1)
            self.read_opts[key] = (mode, n, e)
            mode.trace_add("write", lambda *a: self._read_opt_changed())
            n.trace_add("write", lambda *a: self.mark_dirty())
        ttk.Label(g, text="Bit Diagnostic için N, Word sayısıdır (her Word 32 Bit). En yeni kayıtlar okunur.",
                  foreground="gray").grid(row=3, column=0, columnspan=3, sticky="w", padx=4)
        self.verify_sel = tk.BooleanVar(value=True)
        ttk.Checkbutton(g, text="BRAM adres seçimini geri okuyarak doğrula", variable=self.verify_sel,
                        command=self.mark_dirty).grid(row=4, column=0, columnspan=3, sticky="w", padx=4)
        ttk.Label(g, text="Okuma süresince RX read mode açık tutulur (kayıtlar dondurulur).", foreground="gray").grid(
            row=5, column=0, columnspan=3, sticky="w", padx=4)
        g = ttk.LabelFrame(left, text="Okuma ve yazma dosyaları"); g.pack(fill=tk.X, pady=3)
        ent(g, 0, 0, "Klasör", "out_dir", 30)
        ttk.Button(g, text="…", width=3, command=self._pick_out).grid(row=0, column=2)
        self.auto_txt = tk.BooleanVar(value=True)
        ttk.Checkbutton(g, text="TTL/Excel txt dosyalarını da yaz", variable=self.auto_txt).grid(row=1, column=0, columnspan=3, sticky="w")
        self.auto_write_log = tk.BooleanVar(value=True)
        ttk.Checkbutton(g, text="Register yazma logunu da kaydet", variable=self.auto_write_log).grid(row=2, column=0, columnspan=3, sticky="w")

        bar = ttk.Frame(right); bar.pack(fill=tk.X)
        self.btns = []

        row1, row2 = ttk.Frame(bar), ttk.Frame(bar)
        row1.pack(fill=tk.X); row2.pack(fill=tk.X, pady=(4, 0))

        def group(parent, title, buttons):
            g = ttk.LabelFrame(parent, text=title, padding=6); g.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
            for txt, fn in buttons:
                b = ttk.Button(g, text=txt, command=fn); b.pack(side=tk.LEFT, padx=2); self.btns.append(b)
            return g

        g = group(row1, "Bağlantı", (("Bağlan", self.do_connect), ("IP reset", self.do_ip_reset)))
        ttk.Button(g, text="Bağlantıyı kes", command=self.do_disconnect).pack(side=tk.LEFT, padx=2)
        ttk.Button(g, text="Durdur", command=self.do_stop).pack(side=tk.LEFT, padx=2)
        self.conn_lbl = ttk.Label(g, text="● Bağlı değil", foreground="#C00000"); self.conn_lbl.pack(side=tk.LEFT, padx=(8, 2))
        group(row2, "RX", (("RX Config gönder", self.do_send_cfg), ("RX verilerini oku", self.do_read), ("Tümünü çalıştır", self.do_all)))
        group(row2, "TX", (("TX Config gönder", self.do_send_tx_cfg), ("TX Canlı Kontrol…", self.open_tx_live)))
        self.prog = ttk.Progressbar(right, mode="determinate"); self.prog.pack(fill=tk.X, pady=4)
        lf = ttk.Frame(right); lf.pack(fill=tk.BOTH, expand=True)
        self.log_txt = tk.Text(lf, font=MONO_FONT, bg="#101010", fg="#00FF00", insertbackground="white", wrap=tk.NONE)
        sb = ttk.Scrollbar(lf, command=self.log_txt.yview); self.log_txt.configure(yscrollcommand=sb.set)
        self.log_txt.pack(side=tk.LEFT, fill=tk.BOTH, expand=True); sb.pack(side=tk.LEFT, fill=tk.Y)
        bar2 = ttk.Frame(right); bar2.pack(fill=tk.X)
        ttk.Button(bar2, text="Logu temizle", command=lambda: self.log_txt.delete("1.0", tk.END)).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(bar2, text="Logu kaydet…", command=self._save_log).pack(side=tk.LEFT, padx=2)
        self.verbose = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar2, text="Okumada tüm TX/RX'i logla", variable=self.verbose).pack(side=tk.LEFT, padx=12)

    def _pick_out(self):
        d = filedialog.askdirectory()
        if d:
            self.lv["out_dir"].set(d)

    def _log_write(self, addr, value, frame, rx):
        now = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.write_log.append(f"{now}\tRegister {addr}\tDeğer 0x{int(value):08X}\tTX: {hx(frame)}\tRX: {hx(rx)}")

    def _flush_write_log(self):
        """Biriken yazma kayıtlarını okuma klasöründeki log dosyasına ekler."""
        lines, self.write_log = self.write_log, []
        if not lines or not self.auto_write_log.get():
            return
        try:
            os.makedirs(self.ls.out_dir, exist_ok=True)
            if self.write_log_path is None:
                name = datetime.datetime.now().strftime("yazma_log_%Y%m%d_%H%M%S.txt")
                self.write_log_path = os.path.join(self.ls.out_dir, name)
                self.log(f"Yazma logu: {self.write_log_path}")
            with open(self.write_log_path, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError as e:
            self.log(f"Yazma logu yazılamadı: {e}")

    def do_send_tx_cfg(self):
        def job():
            L = self._ensure_link(); L.stop_flag.clear()
            L.send_config([(n, a, v) for n, a, v, _, _ in self.job_tx["regs"]], title="TX Config")
            return "tx_cfg"
        self._run("TX Config gönderiliyor", job, need_tx=True)

    def do_ip_reset(self):
        if messagebox.askyesno(APP, "ARINC 429 IP bloğu resetlensin mi? (cfg_reset 1 sonra 0 yazılır)"):
            self.tx_write("IP reset", [("ip_reset", 1), ("ip_reset", 0)], verify=False)

    def _fill_tx(self):
        try:
            self.res_tx = compute_tx(self.ci, getattr(self, "tx_override", "Kapalı"))
        except ValueError as e:
            self.res_tx = None
            for tv in (self.tv_tx_regs, self.tv_tx_chk):
                tv.delete(*tv.get_children())
            self.tx_chk_lbl.configure(text=f"TX Config hesaplanamadı: {e}", foreground="#C00000"); self.tx_info.configure(text="")
            return
        tx = self.res_tx
        fill_tree(self.tv_tx_regs, [["" if c is None else c for c in r] for r in tx["regs"]],
                  ["fail" if r[2] is None or not r[1] else "" for r in tx["regs"]])
        fill_tree(self.tv_tx_chk, [[n, "OK" if ok else "UYARI"] for n, ok in tx["checks"]], ["ok" if ok else "fail" for _, ok in tx["checks"]])
        bad = sum(1 for _, ok in tx["checks"] if not ok)
        self.tx_chk_lbl.configure(text=f"UYARI: {bad} TX kontrolü sağlanmıyor." if bad else f"Tüm TX kontrolleri sağlanıyor ({len(tx['checks'])}/{len(tx['checks'])}).",
                                  foreground="#C00000" if bad else "#006100")
        self.tx_info.configure(text=tx["text"])

    def open_tx_live(self):
        win = getattr(self, "tx_win", None)
        if win is not None and win.winfo_exists():
            win.lift(); win.focus_set(); return
        from .txwindow import TxLiveWindow
        self.tx_win = TxLiveWindow(self)

    def tx_write(self, title, writes, parent=None, on_done=None, quiet=False, verify=True):
        """TX Register'larına [(anahtar, değer)] yazar. Başlatılamazsa False döner."""
        regs = self.ci.regmap.tx_regs
        missing = [k for k, _ in writes if not regs.get(k)]
        if missing:
            from .regmap import TX_REGISTERS
            names = dict(TX_REGISTERS)
            messagebox.showerror(APP, "Şu TX Register adresleri girilmemiş:\n" + "\n".join(names[k] for k in missing)
                                 + "\n\nKomut ve Register Düzenleyici → TX ve kontrol Register'ları", parent=parent)
            return False
        if self.busy:
            messagebox.showinfo(APP, "Seri port işlemi sürüyor.", parent=parent); return False
        pairs = [(k, regs[k], v) for k, v in writes]
        no_verify = {"tx_ext_valid", "ip_reset"}         # darbe olarak yazılanlar

        def job():
            L = self._ensure_link(); L.stop_flag.clear()
            bad = []
            for key, addr, value in pairs:
                L.write_reg(addr, value, quiet)
                if verify and key not in no_verify:
                    got = L.read_reg(addr, quiet)
                    if got != value:
                        bad.append(f"{addr}: yazılan {value}, okunan {got}")
            if bad:
                raise LinkError("Geri okuma uyuşmadı: " + "; ".join(bad))
            return "tx"
        self._job_cb = on_done
        if not self._run(title, job, fresh=False):
            self._job_cb = None
            return False
        return True

    def _save_log(self):
        p = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Metin", "*.txt")])
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.log_txt.get("1.0", tk.END))

    def log(self, s):           # worker thread'den güvenli
        self.q.put(("log", s))

    def _poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "log":
                    self.log_txt.insert(tk.END, val + "\n"); self.log_txt.see(tk.END)
                elif kind == "prog":
                    d, t, m = val; self.prog.configure(maximum=max(t, 1), value=d); self.status.set(m)
                elif kind == "done":
                    self._job_done(*val)
        except queue.Empty:
            pass
        self.after(50, self._poll)

    def _set_busy(self, b):
        self.busy = b
        for x in self.btns:
            x.configure(state=tk.DISABLED if b else tk.NORMAL)

    def _run(self, name, fn, fresh=True, need_tx=False):
        """Seri işlemi başlatır; başlayamazsa False döner. fresh: önce formdan yeniden hesapla."""
        if self.busy:
            return False
        if fresh:
            if self._recalc_job:
                self.after_cancel(self._recalc_job)
            self.recalc()
            if self._calc_error:
                messagebox.showerror(APP, f"İşlem başlatılmadı, girişleri düzeltin:\n{self._calc_error}"); return False
        elif not self._commit_form():
            return False
        if need_tx and (self.res_tx is None or self.res_tx["errors"]):
            messagebox.showerror(APP, "TX Config gönderilemez:\n" + ("\n".join(self.res_tx["errors"][:8]) if self.res_tx else self.tx_chk_lbl.cget("text")))
            return False
        self.job_tx = getattr(self, "res_tx", None)
        self.job_ls, self.job_regmap = copy.deepcopy(self.ls), copy.deepcopy(self.ci.regmap)   # işlem sürerken form değişse de etkilenmez
        self.job_res, self.job_mhz = self.res, self.ci.clk_mhz
        self._set_busy(True); self.status.set(f"{name}…")

        def work():
            try:
                out = fn()
                self.q.put(("done", (name, True, out)))
            except Exception as e:
                self.q.put(("log", f"HATA: {e}"))
                self.q.put(("done", (name, False, None)))
        threading.Thread(target=work, daemon=True).start()
        return True

    def _ensure_link(self):
        if self.link and self.link.ser:
            self.link.st, self.link.regmap = self.job_ls, self.job_regmap
            if self.link.opened == self.link.port_settings():
                return self.link
            self.log("Port ayarları değişti, bağlantı yeniden kuruluyor.")
            self.link.close()
        self.link = Link(self.job_ls, log=self.log, regmap=self.job_regmap)
        self.link.on_write = self._log_write
        self.link.open()
        if not self.link.handshake():
            self.link.close()
            raise LinkError("Bağlantı kurulamadı (handshake).")
        return self.link

    def _read_opt_changed(self):
        for mode, _, e in self.read_opts.values():
            e.grid() if mode.get() == "Son N kayıt" else e.grid_remove()
        self.mark_dirty()

    def _cfg_regs(self):
        bad = [r[0] for r in self.job_res.regs if r[2] is None]
        if bad:
            raise LinkError("Değeri hesaplanamayan Register var: " + ", ".join(bad))
        return [(n, a, v) for n, a, v, _, _ in self.job_res.regs]

    def do_connect(self):
        def f():
            if self.link:
                self.link.close(); self.link = None
            self._ensure_link(); return "connected"
        self._run("Bağlanılıyor", f)

    def do_send_cfg(self):
        def f():
            L = self._ensure_link(); L.stop_flag.clear()
            L.send_config(self._cfg_regs()); return "cfg"
        self._run("RX Config gönderiliyor", f)

    def do_read(self):
        quiet = not self.verbose.get()      # Tk değişkeni yalnızca ana thread'de okunur
        def f():
            L = self._ensure_link(); L.stop_flag.clear()
            prog = lambda d, t, m: self.q.put(("prog", (d, t, m)))
            return L.read_all(prog, quiet=quiet)
        self._run("RX verileri okunuyor", f)

    def do_all(self):
        quiet = not self.verbose.get()      # Tk değişkeni yalnızca ana thread'de okunur
        def f():
            if self.link:
                self.link.close(); self.link = None
            L = self._ensure_link(); L.stop_flag.clear()
            L.send_config(self._cfg_regs())
            prog = lambda d, t, m: self.q.put(("prog", (d, t, m)))
            return L.read_all(prog, quiet=quiet)
        self._run("Bağlan + RX Config + RX okuma", f)

    def do_stop(self):
        if self.link:
            self.link.stop_flag.set()

    def do_disconnect(self):
        if self.busy:
            self.do_stop(); return
        if self.link:
            self.link.close(); self.link = None
        self._conn_state()

    def _conn_state(self):
        ok = bool(self.link and self.link.ser)
        self.conn_lbl.configure(text="● Bağlı" if ok else "● Bağlı değil", foreground="#008000" if ok else "#C00000")

    def _job_done(self, name, ok, out):
        self._set_busy(False); self._conn_state()
        self._flush_write_log()
        cb, self._job_cb = self._job_cb, None
        if cb:
            cb(ok)
        if not ok:
            self.status.set(f"{name}: başarısız (log'a bakın)."); return
        self.status.set(f"{name}: tamam.")
        if isinstance(out, dict) and "words" in out:
            s = P.new_session(out, self.ci, self.ls, self.ds)
            s["clk_mhz"] = self.job_mhz
            self.add_session(s, save_file=True)
            self.nb.select(2)

    # =============================================================== oturumlar
    def add_session(self, s, save_file):
        names = {x["name"] for x in self.sessions}
        base, i = s["name"], 2
        while s["name"] in names:
            s["name"] = f"{base}_{i}"; i += 1
        if save_file:
            try:
                os.makedirs(self.ls.out_dir, exist_ok=True)
                p = os.path.join(self.ls.out_dir, s["name"] + ".a429read")
                P.save_session(p, s)
                self.log(f"Okuma kaydedildi: {p}")
                if self.auto_txt.get():
                    d = os.path.join(self.ls.out_dir, s["name"] + "_txt"); os.makedirs(d, exist_ok=True)
                    for fn, txt in export_txt(s).items():
                        with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
                            f.write(txt + "\n")
            except Exception as e:
                self.log(f"Okuma dosyası yazılamadı: {e}")
        self.sessions.append(s); self.cur_session = s; self.mark_dirty()
        self.refresh_sessions()

    def refresh_sessions(self):
        names = [s["name"] for s in self.sessions]
        self.cb_sess.configure(values=names)
        self.sess_var.set(self.cur_session["name"] if self.cur_session else "")
        self.refresh_read()

    def _sel_session(self, *_):
        n = self.sess_var.get()
        for s in self.sessions:
            if s["name"] == n:
                self.cur_session = s
        self.refresh_read()

    def _del_session(self):
        if not self.cur_session or not messagebox.askyesno(APP, f"'{self.cur_session['name']}' projeden çıkarılsın mı?"):
            return
        self.sessions.remove(self.cur_session)
        self.cur_session = self.sessions[-1] if self.sessions else None
        self.mark_dirty(); self.refresh_sessions()

    def _rename_session(self):
        if not self.cur_session:
            return
        top = tk.Toplevel(self); top.title("Yeniden adlandır")
        var = tk.StringVar(value=self.cur_session["name"])
        ttk.Entry(top, textvariable=var, width=40).pack(padx=8, pady=8)

        def ok():
            name = var.get().strip() or self.cur_session["name"]
            if any(x is not self.cur_session and x["name"] == name for x in self.sessions):
                messagebox.showerror(APP, f"'{name}' adında bir okuma var.", parent=top); return
            self.cur_session["name"] = name
            top.destroy(); self.mark_dirty(); self.refresh_sessions()
        ttk.Button(top, text="Tamam", command=ok).pack(pady=(0, 8))

    # =============================================================== sekme: Okuma
    def _tab_read(self, nb):
        t = ttk.Frame(nb); nb.add(t, text="RX Okunan Veriler")
        bar = ttk.Frame(t); bar.pack(fill=tk.X, padx=6, pady=4)
        ttk.Label(bar, text="Okuma:").pack(side=tk.LEFT)
        self.sess_var = tk.StringVar()
        self.cb_sess = ttk.Combobox(bar, textvariable=self.sess_var, width=34, state="readonly")
        self.cb_sess.pack(side=tk.LEFT, padx=4); self.cb_sess.bind("<<ComboboxSelected>>", self._sel_session)
        ttk.Button(bar, text="Aç…", command=self.open_read).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Yeniden adlandır", command=self._rename_session).pack(side=tk.LEFT, padx=2)
        ttk.Button(bar, text="Projeden çıkar", command=self._del_session).pack(side=tk.LEFT, padx=2)
        ttk.Separator(bar, orient=tk.VERTICAL).pack(side=tk.LEFT, fill=tk.Y, padx=8)
        self.dv_par = tk.StringVar(value="Odd Parity")
        ttk.Label(bar, text="Parity:").pack(side=tk.LEFT)
        ttk.Combobox(bar, textvariable=self.dv_par, values=["Odd Parity", "Even Parity"], width=12, state="readonly").pack(side=tk.LEFT, padx=2)
        ttk.Label(bar, text="Timestamp toleransı (%):").pack(side=tk.LEFT, padx=(8, 2))
        self.dv_tol = tk.StringVar(value="1"); ttk.Entry(bar, textvariable=self.dv_tol, width=5).pack(side=tk.LEFT)
        ttk.Label(bar, text="Veri clock'u (MHz):").pack(side=tk.LEFT, padx=(8, 2))
        self.dv_clk = tk.StringVar(); self._clk_sync = False
        ttk.Entry(bar, textvariable=self.dv_clk, width=8).pack(side=tk.LEFT)
        self.dv_clk.trace_add("write", lambda *a: self._data_clock_changed())
        ttk.Label(bar, text="Limitler güncel Config'den alınır", foreground="gray").pack(side=tk.LEFT, padx=8)
        for v in (self.dv_par, self.dv_tol):
            v.trace_add("write", lambda *a: self.refresh_read())
        sub = ttk.Notebook(t); sub.pack(fill=tk.BOTH, expand=True); self.read_nb = sub

        def unitbar(fr, var):
            b = ttk.Frame(fr); b.pack(fill=tk.X)
            ttk.Label(b, text="Zaman birimi:").pack(side=tk.LEFT, padx=4)
            ttk.Combobox(b, textvariable=var, values=TIME_UNITS + ["s"], width=6, state="readonly").pack(side=tk.LEFT)
            var.trace_add("write", lambda *a: self.refresh_read())
            return b

        # word listesi
        a = ttk.Frame(sub); sub.add(a, text="Word Listesi")
        self.u_word = tk.StringVar(value="µs"); unitbar(a, self.u_word)
        self.tv_word = CellTable(a, ["Word No", "Timestamp", "Önceki Word'den geçen süre", "Label (octal)", "SDI", "Data (hex)", "SSM",
                                     "Parity", "Word Gap", "Gap Glitch Error", "ARINC Word (alım sırası)", "Min Pulse", "Max Pulse",
                                     "Min Bit", "Max Bit", "Toplam Pulse Glitch Error", "Toplam Null Glitch Error", "FAIL Bit sayısı",
                                     "32 Bit toplam süre", "32 Bit + Word Gap", "Timestamp farkı", "Süre farkı"],
                                 [60, 110, 170, 85, 40, 75, 40, 55, 90, 110, 260, 80, 80, 80, 80, 160, 155, 100, 120, 125, 110, 90],
                                 on_double=self._word_to_wave)
        self.tv_word.pack(fill=tk.BOTH, expand=True)
        ttk.Label(a, text="En yeni Word en üsttedir. Dalga formunu açmak için satıra çift tıklayın. Yeşil: PASS, kırmızı: FAIL. Nedenini görmek için hücrenin üzerine gelin veya sağ tıklayın.", foreground="gray").pack(anchor="w")
        # dalga formu
        b = ttk.Frame(sub); sub.add(b, text="Word Dalga Formu")
        bar = ttk.Frame(b); bar.pack(fill=tk.X)
        ttk.Label(bar, text="Word No:").pack(side=tk.LEFT, padx=4)
        self.wv_word = tk.StringVar()
        self.cb_wword = ttk.Combobox(bar, textvariable=self.wv_word, width=10, state="readonly"); self.cb_wword.pack(side=tk.LEFT)
        self.wv_all = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Tüm Word'ler (Bit Diagnostic verisi olmayanlar nominal çizilir)", variable=self.wv_all,
                        command=self.refresh_wave_list).pack(side=tk.LEFT, padx=6)
        self.u_wave = tk.StringVar(value="clk")
        ttk.Label(bar, text="Birim:").pack(side=tk.LEFT, padx=(8, 2))
        ttk.Combobox(bar, textvariable=self.u_wave, values=TIME_UNITS, width=6, state="readonly").pack(side=tk.LEFT)
        self.wv_ts = tk.StringVar(value="Word sonu")
        ttk.Label(bar, text="Timestamp anı:").pack(side=tk.LEFT, padx=(8, 2))
        ttk.Combobox(bar, textvariable=self.wv_ts, values=["Word sonu", "Word başı"], width=10, state="readonly").pack(side=tk.LEFT)
        self.fmtv = {}
        for key, lab, vals in (("label_fmt", "Label", ["oct", "hex", "dec"]), ("sdi_fmt", "SDI", ["dec", "hex"]),
                               ("data_fmt", "Data", ["hex", "dec", "oct"]), ("ssm_fmt", "SSM", ["dec", "hex"])):
            ttk.Label(bar, text=f"{lab}:").pack(side=tk.LEFT, padx=(8, 2))
            var = tk.StringVar(value=vals[0]); self.fmtv[key] = var
            ttk.Combobox(bar, textvariable=var, values=vals, width=5, state="readonly").pack(side=tk.LEFT)
        for v in [self.wv_word, self.u_wave, self.wv_ts] + list(self.fmtv.values()):
            v.trace_add("write", lambda *a: self.draw_wave())
        self.fp_wave = FigPanel(b, (22, 7)); self.fp_wave.pack(fill=tk.BOTH, expand=True)
        # bit diag
        c = ttk.Frame(sub); sub.add(c, text="Bit Diagnostic")
        self.u_bit = tk.StringVar(value="µs"); unitbar(c, self.u_bit)
        ttk.Label(c, text="Yeşil: PASS, kırmızı: FAIL. Nedenini görmek için hücrenin üzerine gelin veya sağ tıklayın.", foreground="gray").pack(anchor="w", padx=4)
        self.tv_bit = CellTable(c, ["Word No", "Bit No (ARINC)", "Pulse", "Null", "Bit Time (Pulse + Null)", "Pulse Glitch Error",
                                    "Null Glitch Error", "Ham Register değerleri (hex)"], [60, 100, 90, 90, 150, 120, 115, 300])
        self.tv_bit.pack(fill=tk.BOTH, expand=True)
        # error
        d = ttk.Frame(sub); sub.add(d, text="Error Listesi")
        self.u_err = tk.StringVar(value="ms"); unitbar(d, self.u_err)
        ttk.Label(d, text="Yeşil: PASS, kırmızı: FAIL. Nedenini görmek için hücrenin üzerine gelin veya sağ tıklayın.", foreground="gray").pack(anchor="w", padx=4)
        self.tv_err = CellTable(d, ["No", "Timestamp", "Önceki Error'dan geçen süre", "Aktif Error'lar", "Error Address",
                                    "Error Data (hex)", "Error Data (decimal)"], [40, 110, 175, 320, 100, 115, 135])
        self.tv_err.pack(fill=tk.BOTH, expand=True)
        # istatistik
        e = ttk.Frame(sub); sub.add(e, text="İstatistik")
        fr, self.tv_st = make_tree(e, ["Parametre", "Değer", "Açıklama"], [290, 160, 560], 14); fr.pack(fill=tk.X, padx=4, pady=4)
        fr, self.tv_stc = make_tree(e, ["Tutarlılık kontrolü", "Sonuç"], [320, 160], 5); fr.pack(fill=tk.X, padx=4, pady=4)

    def _tab_tx_sent(self, nb):
        t = ttk.Frame(nb, padding=12); nb.add(t, text="TX Gönderilen Veriler")
        ttk.Label(t, text="TX gönderilen veriler burada listelenecek (sonraki aşama).", font=BOLD_FONT).pack(anchor="w")

    def _limits(self, session):
        return Limits.from_result(self.res, self.ci.clk_mhz).for_clock(session_mhz(session, self.ci.clk_mhz))

    def _show_data_clock(self, mhz):
        try:
            same = mhz is not None and float(self.dv_clk.get().replace(",", ".")) == mhz
        except ValueError:
            same = False
        if not same:
            self._clk_sync = True
            self.dv_clk.set("" if mhz is None else f"{mhz:g}")
            self._clk_sync = False

    def _data_clock_changed(self):
        if self._clk_sync or not self.cur_session:
            return
        try:
            mhz = float(self.dv_clk.get().replace(",", "."))
            if mhz <= 0:
                raise ValueError
        except ValueError:
            self.status.set("Veri clock'u sıfırdan büyük bir sayı olmalı."); return
        self.cur_session["clk_mhz"] = mhz
        self.mark_dirty(); self.refresh_read()

    def _ds(self):
        ds = self.ds
        ds.parity_odd = self.dv_par.get().startswith("Odd")
        try:
            ds.ts_tol = float(self.dv_tol.get().replace(",", ".")) / 100
        except ValueError:
            pass
        ds.ts_at_word_end = self.wv_ts.get() == "Word sonu"
        for k, v in self.fmtv.items():
            setattr(ds, k, v.get())
        return ds

    def refresh_read(self):
        if not hasattr(self, "tv_word") or not self.res:
            return
        s = self.cur_session
        for tv in (self.tv_word, self.tv_bit, self.tv_err):
            tv.set_rows([])
        for tv in (self.tv_st, self.tv_stc):
            tv.delete(*tv.get_children())
        if not s:
            self._show_data_clock(None); self.refresh_wave_list(); return
        lim, ds, mhz = self._limits(s), self._ds(), session_mhz(s, self.ci.clk_mhz)
        self._show_data_clock(mhz)
        u = self.u_word.get(); T = lambda v: ft(v, u, mhz)
        par = "Odd" if ds.parity_odd else "Even"
        rows = []
        for r in decode_words(s, lim, ds):
            def chk(text, key, why):
                return Cell(text, r[key], why) if key in r else Cell(text)
            ones = bin(r["wd"]).count("1") if r.get("wd") is not None else 0
            fails = r.get("fail_list")
            rows.append([r["no"], chk(T(r["ts"]), "ts_order_ok", "Timestamp, önceki Word'den büyük olmalı. Aynı veya küçük değer, adres seçme yazmasının kaybolduğunu gösterebilir."),
                         T(r.get("dt")), f"{r['label']:03o}" if "label" in r else "?",
                         r.get("sdi", ""), f"{r['data']:05X}" if "data" in r else "?", r.get("ssm", ""),
                         chk(r.get("p", "?"), "parity_ok", f"{par} Parity bekleniyor; Word içindeki 1 sayısı: {ones}."),
                         chk(T(r["gap"]), "gap_ok", f"Word Gap = {T(r['gap'])}, alt limit 4 × Min Bit = {T(4 * lim.minb)}."),
                         chk(r["gerr"] if r["gerr"] is not None else "?", "gerr_ok", f"Gap Glitch Error = {r['gerr']}, limit ≤ {lim.gap_err}."),
                         r.get("bin", ""), T(r.get("minp")), T(r.get("maxp")), T(r.get("minb")), T(r.get("maxb")),
                         r.get("sum_perr", ""), r.get("sum_nerr", ""),
                         Cell("") if fails is None else Cell(len(fails), not fails, (
                             "Limit dışı Bit yok." if not fails else
                             "Limit dışı Bit'ler: " + ", ".join(map(str, fails)) + " (ayrıntı: Bit Diagnostic sekmesi).")),
                         T(r.get("tot_bits")), T(r.get("bits_gap")), T(r.get("dts")),
                         chk(T(r.get("diff")), "ts_ok", f"|Süre farkı| = {T(abs(r.get('diff') or 0))}, limit = %{ds.ts_tol * 100:g} × Timestamp farkı = {T(ds.ts_tol * (r.get('dts') or 0))}.")])
        self.tv_word.set_rows(rows)
        u = self.u_bit.get(); T = lambda v: ft(v, u, mhz)
        rows = []
        for r in decode_bits(s, lim):
            rows.append([r["word"], r["bit"] + 1,
                         Cell(T(r["pulse"]), r["ok_pulse"], f"Pulse = {T(r['pulse'])}, limit {T(lim.minp)} … {T(lim.maxp)}."),
                         T(r["null"]),
                         Cell(T(r["bitlen"]), r["ok_bit"], f"Bit Time (Pulse + Null) = {T(r['bitlen'])}, limit {T(lim.minb)} … {T(lim.maxb)}."),
                         Cell(r["perr"], r["ok_perr"], f"Pulse Glitch Error = {r['perr']}, limit ≤ {lim.pulse_err}."),
                         Cell(r["nerr"], r["ok_nerr"], f"Null Glitch Error = {r['nerr']}, limit ≤ {lim.null_err}."),
                         Cell(" ".join("XXXXXXXX" if x is None else f"{x:08X}" for x in r["raw"]), r["ok_pad"],
                              "Padding kontrolü: Pulse, Null ve Glitch Error değerleri 16 bit içinde olmalı.")])
        self.tv_bit.set_rows(rows)
        u = self.u_err.get(); T = lambda v: ft(v, u, mhz)
        rows = []
        for i, r in enumerate(decode_errors(s)):
            rows.append([i + 1, T(r["ts"]), T(r["dt"]),
                         Cell(r["active"], r["code_ok"] and not any(r["flags"]), f"Aktif Error'lar: {r['active']}." if r["code_ok"] else "Error Code okunamadı."),
                         Cell(r["addr"], r["pad_ok"], "Padding kontrolü: Error Code 8 bit, Error Address 16 bit içinde olmalı."),
                         " ".join(f"{b:02X}" for b in (r["data"] or 0).to_bytes(4, "big")), r["data"]])
        self.tv_err.set_rows(rows)
        res, chk = stats(s, lim, self.ls.wdepth, self.ls.edepth, self.ls.bit_words)
        fill_tree(self.tv_st, res)
        fill_tree(self.tv_stc, chk, ["fail" if c[1] == "FAIL" else ("ok" if c[1] == "PASS" else "") for c in chk])
        self.refresh_wave_list()

    def refresh_wave_list(self):
        s = self.cur_session
        if not s:
            self.cb_wword.configure(values=[]); self.wv_word.set(""); self.fp_wave.fig.clear(); self.fp_wave.draw(); return
        bm = bits_by_word(s)
        nos = [w["no"] for w in s.get("words", []) if self.wv_all.get() or len(bm.get(w["no"], {})) >= 32]
        self.cb_wword.configure(values=[str(n) for n in nos])
        if self.wv_word.get() not in [str(n) for n in nos]:
            self.wv_word.set(str(nos[0]) if nos else "")
        else:
            self.draw_wave()

    def _word_to_wave(self, row):
        no = self.tv_word.cell_text(row, 0)
        if no not in self.cb_wword.cget("values"):
            self.wv_all.set(True); self.refresh_wave_list()
        self.wv_word.set(no); self.read_nb.select(1)

    def draw_wave(self):
        s = self.cur_session
        if not s or not self.wv_word.get() or not self.res:
            return
        no = int(self.wv_word.get())
        lim, ds = self._limits(s), self._ds()
        rows = {r["no"]: r for r in decode_words(s, lim, ds)}
        if no not in rows:
            return
        bm = bits_by_word(s).get(no, {})
        bmap = {b: ((v["w"][0] or 0), (v["w"][2] or 0)) for b, v in bm.items()}
        mhz = session_mhz(s, self.ci.clk_mhz)
        f = mhz / self.ci.clk_mhz
        nom = (round(self.res.nom_clk[0] * f), round(self.res.nom_clk[2] * f))
        try:
            draw_word(self.fp_wave.fig, rows[no], bmap, mhz, self.u_wave.get(), ds, nom); self.fp_wave.draw()
        except Exception as e:
            self.status.set(f"Dalga formu çizilemedi: {e}")

    # =============================================================== form ↔ model
    def load_to_form(self):
        self.ls.port = native_port(self.ls.port)
        self.ls.out_dir = native_dir(self.ls.out_dir)
        ci, v = self.ci, self.v
        self._loading = True
        self._refresh_profile_combos(); v["ic_profile"].set(ci.ic.name); v["tx_profile"].set(self._current("tx_profile").name)
        v["clk_mhz"].set(f"{ci.clk_mhz:g}"); v["profile"].set(ci.profile); v["ppm"].set(f"{ci.ppm:g}")
        self.cb_fpga.configure(values=[r[0] for r in ci.fpga_table]); v["fpga_std"].set(ci.fpga_std)
        for vs, r in zip(self.fpv, ci.fpga_table):
            vs[0].set(r[0]); vs[1].set(f"{float(r[1]):g}"); vs[2].set(f"{float(r[2]):g}")
        for k, var in self.icx.items():
            var.set(f"{getattr(ci.ic, k):g}")
        v["err"].set(f"{ci.err * 100:g}"); v["half_ref"].set(ci.half_ref)
        v["gf_mode"].set(GF_CLOCK if ci.gf_mode == "clock" else GF_RATIO); v["gf_ref"].set(ci.gf_ref)
        v["gf_ratio"].set(f"{ci.gf_ratio * 100:g}"); v["gf_clock"].set(str(ci.gf_clock))
        v["pulse_glitch_pct"].set(f"{ci.pulse_glitch_pct * 100:g}"); v["null_glitch_pct"].set(f"{ci.null_glitch_pct * 100:g}")
        v["gap_glitch_pct"].set(f"{ci.gap_glitch_pct * 100:g}"); v["glitch_base"].set(ci.glitch_base)
        for k, vs in self.icv.items():
            for var, x in zip(vs, getattr(ci.ic, k)):
                var.set(f"{x:g}")
        for k, var in self.pv.items():
            var.set(f"{getattr(ci.get_profile(), k):g}")
        self._fill_arinc_rows()
        ls = self.ls
        for k, var in self.lv.items():
            val = getattr(ls, k)
            var.set(",".join(val) if isinstance(val, list) else (f"{val:g}" if isinstance(val, float) else str(val)))
        v["ip_port"].set(ci.regmap.ip_port); self.verify_sel.set(self.ls.verify_select)
        names = {b: a for a, b in READ_MODES.items()}
        for key, (mode, n, _) in self.read_opts.items():
            mode.set(names[getattr(ls, f"read_{key}")]); n.set(str(getattr(ls, f"read_{key}_n")))
        self.dv_par.set("Odd Parity" if self.ds.parity_odd else "Even Parity")
        self.dv_tol.set(f"{self.ds.ts_tol * 100:g}")
        self.wv_ts.set("Word sonu" if self.ds.ts_at_word_end else "Word başı")
        for k, var in self.fmtv.items():
            var.set(getattr(self.ds, k))
        self._loading = False
        self.dirty_after_load = False
        win = getattr(self, "tx_win", None)
        if win is not None and win.winfo_exists():
            win.load()

    def form_to_model(self):
        ci, v = self.ci, self.v
        num = lambda key: _to_float(v[key].get(), key)
        ci.clk_mhz = num("clk_mhz"); ci.err = num("err") / 100
        for k, var in self.pv.items():
            setattr(ci.get_profile(), k, _to_float(var.get(), k))
        ci.ppm = num("ppm")
        old = [r[0] for r in ci.fpga_table]
        ci.fpga_table = [[vs[0].get().strip() or old[i], _to_float(vs[1].get(), "FPGA VIL MAX"),
                          _to_float(vs[2].get(), "FPGA VIH MIN")] for i, vs in enumerate(self.fpv)]
        names = [r[0] for r in ci.fpga_table]
        sel = v["fpga_std"].get()
        if sel in old and sel not in names:
            sel = names[old.index(sel)]
        ci.fpga_std = sel if sel in names else names[0]
        if list(self.cb_fpga.cget("values")) != names:
            self.cb_fpga.configure(values=names)
        for k, var in self.icx.items():
            setattr(ci.ic, k, _to_float(var.get(), k))
        ci.half_ref = v["half_ref"].get()
        ci.gf_mode = "clock" if v["gf_mode"].get() == GF_CLOCK else "ratio"; ci.gf_ref = v["gf_ref"].get()
        if ci.gf_mode == "clock":           # yalnızca görünen alan okunur
            ci.gf_clock = int(num("gf_clock"))
        else:
            ci.gf_ratio = num("gf_ratio") / 100
        ci.pulse_glitch_pct = num("pulse_glitch_pct") / 100; ci.null_glitch_pct = num("null_glitch_pct") / 100
        ci.gap_glitch_pct = num("gap_glitch_pct") / 100; ci.glitch_base = v["glitch_base"].get()
        for k, vs in self.icv.items():
            setattr(ci.ic, k, tuple(_to_float(x.get(), k) for x in vs))
        ls = self.ls
        for k, var in self.lv.items():
            cur = getattr(ls, k); val = var.get().strip()
            if isinstance(cur, list):
                setattr(ls, k, [x.strip().upper() for x in val.split(",") if x.strip()])
            elif isinstance(cur, bool):
                setattr(ls, k, val.lower() in ("1", "true", "evet"))
            elif isinstance(cur, int):
                setattr(ls, k, int(_to_float(val, k)))
            elif isinstance(cur, float):
                setattr(ls, k, _to_float(val, k))
            else:
                setattr(ls, k, val)
        for name, text in (("Handshake dizisi", ls.handshake), ("Handshake cevabı", ls.hs_response)):
            try:
                ok = bool(bytes.fromhex(text))
            except ValueError:
                ok = False
            if not ok:
                raise ValueError(f"{name} geçerli hex Byte'lar içermeli (ör. 00 11 AA).")
        try:
            ci.regmap.ip_port = norm_addr(v["ip_port"].get())
        except ValueError:
            raise ValueError("Hedef IP portu hex olmalı (ör. 01).") from None
        ls.verify_select = self.verify_sel.get()
        for key, (mode, n, _) in self.read_opts.items():
            m = READ_MODES[mode.get()]
            setattr(ls, f"read_{key}", m)
            if m == "last":
                count = int(_to_float(n.get(), "Okunacak kayıt sayısı"))
                if count < 1:
                    raise ValueError("Okunacak kayıt sayısı en az 1 olmalı.")
                setattr(ls, f"read_{key}_n", count)
        self._ds()

    def schedule_recalc(self):
        if getattr(self, "_loading", False):
            return
        self.mark_dirty()
        if self._recalc_job:
            self.after_cancel(self._recalc_job)
        self._recalc_job = self.after(300, self.recalc)

    def recalc(self):
        self._recalc_job, self._calc_error = None, None
        try:
            self.form_to_model()
            self.res = compute(self.ci)
        except Exception as e:
            self._calc_error = str(e)
            self.status.set(f"Giriş hatası: {e}"); return
        r = self.res
        fill_tree(self.tv_regs, [["" if c is None else c for c in x] for x in r.regs],
                  ["fail" if x[2] is None else "" for x in r.regs])
        f = lambda x: "" if x is None else f"{x:.3f}"
        fill_tree(self.tv_mid, [[k, f(a), f(b), f(c)] for k, (a, b, c) in r.rows.items()])
        fill_tree(self.tv_dur, [[k, f"{us:.3f}", f"{clk:,}"] for k, (us, clk) in r.dur.items()]
                  + [[k, f"{r.vars[key] / self.ci.clk_mhz:.3f}", f"{r.vars[key]:,}"] for k, key in DERIVED_ROWS])
        vil, vih = self.ci.get_fpga()
        self._update_summaries(vil, vih)
        fill_tree(self.tv_chk, [[n, "OK" if ok else "UYARI"] for n, ok in r.checks],
                  ["ok" if ok else "fail" for _, ok in r.checks])
        bad = sum(1 for _, ok in r.checks if not ok)
        self.chk_lbl.configure(text=(f"UYARI: {bad} RX kontrolü sağlanmıyor (ayrıntı aşağıda, Kontroller sekmesinde)." if bad
                                     else f"Tüm RX kontrolleri sağlanıyor ({len(r.checks)}/{len(r.checks)})."),
                               foreground="#C00000" if bad else "#006100")
        self._fill_tx()
        self.draw_cfg_charts()
        self.refresh_read()
        self.status.set("RX Config hesaplandı.")


def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
