"""Komut yapısı ve Register düzenleyici penceresi."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from .regmap import TX_REGISTERS, RegisterMap, WriteReg, ReadReg, FrameError, FormulaError, build_frame, evaluate, hexstr, norm_addr
from .protocol import LinkSettings
from .model import VARIABLES

ENDIANS = {"Big Endian": "big", "Little Endian": "little"}
READ_GROUPS = [
    ("Sayaçlar ve Timestamp", [("reg_wcnt", "Word Count"), ("reg_ecnt", "Error Count"),
                               ("reg_ts_lsb", "System Timestamp LSB"), ("reg_ts_msb", "System Timestamp MSB")]),
    ("Word BRAM", [("reg_waddr", "Adres seçimi"), (("reg_w", 0), "Timestamp MSB"), (("reg_w", 1), "Timestamp LSB"),
                   (("reg_w", 2), "Data"), (("reg_w", 3), "Word Gap"), (("reg_w", 4), "Gap Glitch Error"),
                   ("wdepth", "BRAM derinliği")]),
    ("Error BRAM", [("reg_eaddr", "Adres seçimi"), (("reg_e", 0), "Timestamp MSB"), (("reg_e", 1), "Timestamp LSB"),
                    (("reg_e", 2), "Error Code"), (("reg_e", 3), "Error Address"), (("reg_e", 4), "Error Data"),
                    ("edepth", "BRAM derinliği")]),
    ("Bit Diagnostic BRAM", [("reg_baddr", "Adres seçimi"), (("reg_b", 0), "Pulse"), (("reg_b", 1), "Pulse Glitch Error"),
                             (("reg_b", 2), "Null"), (("reg_b", 3), "Null Glitch Error"), ("bit_words", "Word sayısı")]),
]
DECIMAL_FIELDS = ("wdepth", "edepth", "bit_words")


def _get(ls, key):
    return getattr(ls, key[0])[key[1]] if isinstance(key, tuple) else getattr(ls, key)


class _RegDialog(tk.Toplevel):
    """Tek Register düzenleme. variables verilirse yazma Register'ı (formül), yoksa okuma Register'ı."""

    def __init__(self, parent, title, reg, variables, on_ok):
        super().__init__(parent)
        self.title(title); self.transient(parent); self.resizable(False, False)
        self.parent, self.reg, self.variables, self.on_ok = parent, reg, variables, on_ok
        f = ttk.Frame(self, padding=10); f.pack(fill=tk.BOTH, expand=True)
        self.name = tk.StringVar(value=reg.name); self.addr = tk.StringVar(value=reg.addr)
        ttk.Label(f, text="Register adı").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(f, textvariable=self.name, width=46).grid(row=0, column=1, sticky="w", pady=2)
        ttk.Label(f, text="Adres (hex)").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(f, textvariable=self.addr, width=10).grid(row=1, column=1, sticky="w", pady=2)
        if variables is None:
            self.fmt = tk.StringVar(value=reg.fmt)
            ttk.Label(f, text="Gösterim").grid(row=2, column=0, sticky="w", pady=2)
            ttk.Combobox(f, textvariable=self.fmt, values=["hex", "dec"], width=8, state="readonly").grid(row=2, column=1, sticky="w")
        else:
            self.enabled = tk.BooleanVar(value=reg.enabled)
            self.formula = tk.StringVar(value=reg.formula)
            ttk.Checkbutton(f, text="Config gönderilirken yazılsın", variable=self.enabled).grid(row=2, column=1, sticky="w", pady=2)
            ttk.Label(f, text="Değer formülü").grid(row=3, column=0, sticky="w", pady=2)
            self.ent = ttk.Entry(f, textvariable=self.formula, width=46); self.ent.grid(row=3, column=1, sticky="w", pady=2)
            ttk.Label(f, text="Değişken ekle").grid(row=4, column=0, sticky="w", pady=2)
            self.pick = ttk.Combobox(f, values=[v[0] for v in VARIABLES], width=30, state="readonly")
            self.pick.grid(row=4, column=1, sticky="w", pady=2); self.pick.bind("<<ComboboxSelected>>", self._insert)
            ttk.Label(f, foreground="gray", justify=tk.LEFT, text=(
                "Örnekler:  min_pulse   ·   min_pulse + 2   ·   floor(max_bit * 0.9)   ·   (max_bit << 16) | min_bit\n"
                "İşlemler: + - * / // % & | ^ << >>   İşlevler: floor ceil round min max abs"
            )).grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 2))
            from .gui import BOLD_FONT
            self.result = ttk.Label(f, text="", font=BOLD_FONT)
            self.result.grid(row=6, column=0, columnspan=2, sticky="w", pady=2)
            self.formula.trace_add("write", lambda *a: self._preview()); self._preview()
        bar = ttk.Frame(f); bar.grid(row=9, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(bar, text="İptal", command=self.close).pack(side=tk.RIGHT, padx=2)
        ttk.Button(bar, text="Tamam", command=self.ok).pack(side=tk.RIGHT, padx=2)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(50, self._grab)

    def _grab(self):
        try:
            self.grab_set()
        except tk.TclError:
            pass

    def _insert(self, _=None):
        self.ent.insert(tk.INSERT, self.pick.get()); self.ent.focus_set()

    def _preview(self):
        try:
            v = evaluate(self.formula.get(), self.variables)
            self.result.configure(text=f"Sonuç: {v:,} (0x{v:X})" if v >= 0 else f"Sonuç negatif: {v}", foreground="#006100" if v >= 0 else "#C00000")
        except FormulaError as e:
            self.result.configure(text=str(e), foreground="#C00000")

    def close(self):
        self.destroy()
        try:
            self.parent.grab_set()
        except tk.TclError:
            pass

    def ok(self):
        r = self.reg
        try:
            name, addr = self.name.get().strip(), norm_addr(self.addr.get())
            if not name:
                raise ValueError("Register adı boş olamaz.")
            if self.variables is not None:
                evaluate(self.formula.get(), self.variables)
        except ValueError as e:
            messagebox.showerror("Register", str(e) if "base 16" not in str(e) else "Adres hex olmalı.", parent=self); return
        new = (ReadReg(name, addr, self.fmt.get()) if self.variables is None
               else WriteReg(name, addr, self.formula.get().strip(), self.enabled.get(), getattr(r, "bits", 32)))
        err = self.on_ok(r, new)
        if err:
            messagebox.showerror("Register", err, parent=self); return
        self.close()


class RegisterEditor(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        from .gui import make_tree
        self.make_tree = make_tree
        self.app, self.rm = app, app.ci.regmap.copy()
        self.vars_now = dict(app.res.vars) if app.res else {}
        self.title("Komut ve Register Düzenleyici"); self.transient(app); self.geometry("1180x700"); self.minsize(960, 600)
        nb = ttk.Notebook(self); nb.pack(fill=tk.BOTH, expand=True, padx=6, pady=6); self.nb = nb
        self._tab_cmd(nb); self._tab_write(nb); self._tab_read(nb); self._tab_tx(nb)
        bar = ttk.Frame(self); bar.pack(fill=tk.X, padx=6, pady=(0, 6))
        ttk.Button(bar, text="Varsayılanlara dön", command=self.reset).pack(side=tk.LEFT)
        ttk.Button(bar, text="İptal", command=self.destroy).pack(side=tk.RIGHT, padx=2)
        ttk.Button(bar, text="Uygula", command=self.apply).pack(side=tk.RIGHT, padx=2)
        self.load(); self.after(50, self._grab)

    def _grab(self):
        try:
            self.grab_set()
        except tk.TclError:
            pass

    # ------------------------------------------------------------- komut yapısı
    def _tab_cmd(self, nb):
        t = ttk.Frame(nb, padding=8); nb.add(t, text="Komut Yapısı")
        self.cmd = {k: tk.StringVar() for k in ("write_cmd", "read_cmd", "read_rsp")}
        self.prev = {}
        for i, (k, lab) in enumerate((("write_cmd", "Yazma komutu"), ("read_cmd", "Okuma komutu"), ("read_rsp", "Okuma cevabı"))):
            ttk.Label(t, text=lab).grid(row=i * 2, column=0, sticky="w", padx=(0, 10), pady=(6, 0))
            ttk.Entry(t, textvariable=self.cmd[k], width=50).grid(row=i * 2, column=1, sticky="w", pady=(6, 0))
            self.prev[k] = ttk.Label(t, text=""); self.prev[k].grid(row=i * 2 + 1, column=1, sticky="w")
            self.cmd[k].trace_add("write", lambda *a: self._cmd_changed())
        ttk.Label(t, text="Byte sırası").grid(row=6, column=0, sticky="w", pady=(10, 0))
        self.endian = tk.StringVar()
        ttk.Combobox(t, textvariable=self.endian, values=list(ENDIANS), width=14, state="readonly").grid(row=6, column=1, sticky="w", pady=(10, 0))
        self.endian.trace_add("write", lambda *a: self._cmd_changed())
        ttk.Label(t, foreground="gray", justify=tk.LEFT, text=(
            "Şablonda boşlukla ayrılmış parçalar kullanılır:\n"
            "  İki haneli hex Byte (ör. C3): sabit değer\n"
            "  {IP}: Hedef IP portu; değeri Bağlantı sekmesinden seçilir\n"
            "  {REG}: 1 Byte Register adresi  ·  {REG16}: 2 Byte  ·  {REG32}: 4 Byte\n"
            "  {DATA}: 4 Byte veri  ·  {DATA8}, {DATA16}, {DATA32}, {DATA64}: istenen genişlik\n"
            "Yazma komutunda birer {REG} ve {DATA}, okuma komutunda bir {REG}, okuma cevabında bir {DATA} bulunmalıdır."
        )).grid(row=7, column=0, columnspan=2, sticky="w", pady=(16, 0))

    def _cmd_changed(self):
        if getattr(self, "_loading", False):
            return
        rm = self.rm
        for k, var in self.cmd.items():
            setattr(rm, k, var.get())
        rm.endian = ENDIANS.get(self.endian.get(), "big")
        for k, var in self.cmd.items():
            try:
                b = build_frame(var.get(), 0x11, 0x12345678, rm.endian, rm.ip())
                self.prev[k].configure(text=f"Örnek (IP {rm.ip_port}, Register 11, Data 12345678): {hexstr(b)}", foreground="#006100")
            except FrameError as e:
                self.prev[k].configure(text=str(e), foreground="#C00000")
        self._refresh_write()

    # ------------------------------------------------------------- yazma Register'ları
    def _tab_write(self, nb):
        t = ttk.Frame(nb, padding=6); nb.add(t, text="Yazma Register'ları")
        left = ttk.Frame(t); left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        fr, self.tv_w = self.make_tree(left, ("Aktif", "Register adı", "Adres", "Formül", "Değer", "Yazma komutu"),
                                       [45, 200, 55, 190, 80, 200], 18)
        fr.pack(fill=tk.BOTH, expand=True); self.tv_w.bind("<Double-1>", lambda e: self.edit_write())
        bar = ttk.Frame(left); bar.pack(fill=tk.X, pady=4)
        for txt, fn in (("Yeni Register", self.add_write), ("Düzenle", self.edit_write), ("Sil", self.del_write),
                        ("Yukarı", lambda: self.move_write(-1)), ("Aşağı", lambda: self.move_write(1))):
            ttk.Button(bar, text=txt, command=fn).pack(side=tk.LEFT, padx=2)
        right = ttk.LabelFrame(t, text="Hesaplanan değişkenler"); right.pack(side=tk.LEFT, fill=tk.Y, padx=(6, 0))
        fr, tv = self.make_tree(right, ("Değişken", "Değer", "Açıklama"), [170, 70, 190], 18); fr.pack(fill=tk.BOTH, expand=True)
        for key, desc in VARIABLES:
            tv.insert("", tk.END, values=(key, f"{self.vars_now.get(key, 0):,}", desc))

    def _sel(self, tv):
        s = tv.selection()
        return tv.index(s[0]) if s else None

    def _refresh_write(self, select=None):
        tv = self.tv_w
        tv.delete(*tv.get_children())
        try:
            self.rm.validate()
            ok = True
        except FrameError:
            ok = False
        for r in self.rm.write_regs:
            v, _, cmd, err = self.rm.resolve(r, self.vars_now) if ok else (None, "", "", "Komut şablonu hatalı")
            tv.insert("", tk.END, values=("Evet" if r.enabled else "Hayır", r.name, r.addr, r.formula,
                                          "" if v is None else f"{v:,}", cmd if v is not None else err),
                      tags=("fail",) if v is None else ())
        if select is not None and tv.get_children():
            item = tv.get_children()[select]; tv.selection_set(item); tv.see(item)

    def _store_write(self, old, new):
        others = [r for r in self.rm.write_regs if r is not old]
        if any(r.name == new.name for r in others):
            return f"'{new.name}' adında başka bir Register var."
        if any(r.addr == new.addr for r in others):
            return f"{new.addr} adresi başka bir Register'da kullanılıyor."
        if old in self.rm.write_regs:
            i = self.rm.write_regs.index(old); self.rm.write_regs[i] = new
        else:
            self.rm.write_regs.append(new); i = len(self.rm.write_regs) - 1
        self._refresh_write(i)
        return None

    def add_write(self):
        _RegDialog(self, "Yeni yazma Register'ı", WriteReg("", "", "0"), self.vars_now, self._store_write)

    def edit_write(self):
        i = self._sel(self.tv_w)
        if i is not None:
            _RegDialog(self, "Yazma Register'ını düzenle", self.rm.write_regs[i], self.vars_now, self._store_write)

    def del_write(self):
        i = self._sel(self.tv_w)
        if i is not None:
            del self.rm.write_regs[i]; self._refresh_write()

    def move_write(self, d):
        i, l = self._sel(self.tv_w), self.rm.write_regs
        if i is not None and 0 <= i + d < len(l):
            l[i], l[i + d] = l[i + d], l[i]; self._refresh_write(i + d)

    # ------------------------------------------------------------- okuma Register'ları
    def _tab_read(self, nb):
        t = ttk.Frame(nb, padding=6); nb.add(t, text="Okuma Register'ları")
        top = ttk.Frame(t); top.pack(fill=tk.X)
        self.rv = {}
        for title, items in READ_GROUPS:
            g = ttk.LabelFrame(top, text=title); g.pack(side=tk.LEFT, fill=tk.Y, padx=3)
            for r, (key, lab) in enumerate(items):
                ttk.Label(g, text=lab + (" (hex)" if key not in DECIMAL_FIELDS else "")).grid(row=r, column=0, sticky="w", padx=4, pady=1)
                var = tk.StringVar(); self.rv[key] = var
                ttk.Entry(g, textvariable=var, width=7).grid(row=r, column=1, padx=4, pady=1)
        g = ttk.LabelFrame(t, text="Ek okuma Register'ları (okuma sırasında bir kez okunur, İstatistik sekmesinde görünür)")
        g.pack(fill=tk.BOTH, expand=True, pady=(8, 0))
        fr, self.tv_x = self.make_tree(g, ("Register adı", "Adres", "Gösterim"), [320, 70, 80], 8)
        fr.pack(fill=tk.BOTH, expand=True); self.tv_x.bind("<Double-1>", lambda e: self.edit_read())
        bar = ttk.Frame(g); bar.pack(fill=tk.X, pady=3)
        for txt, fn in (("Yeni Register", self.add_read), ("Düzenle", self.edit_read), ("Sil", self.del_read)):
            ttk.Button(bar, text=txt, command=fn).pack(side=tk.LEFT, padx=2)

    def _refresh_read(self):
        self.tv_x.delete(*self.tv_x.get_children())
        for r in self.rm.extra_read:
            self.tv_x.insert("", tk.END, values=(r.name, r.addr, r.fmt))

    def _store_read(self, old, new):
        others = [r for r in self.rm.extra_read if r is not old]
        if any(r.name == new.name for r in others):
            return f"'{new.name}' adında başka bir Register var."
        if old in self.rm.extra_read:
            self.rm.extra_read[self.rm.extra_read.index(old)] = new
        else:
            self.rm.extra_read.append(new)
        self._refresh_read()
        return None

    def add_read(self):
        _RegDialog(self, "Yeni okuma Register'ı", ReadReg("", ""), None, self._store_read)

    def edit_read(self):
        i = self._sel(self.tv_x)
        if i is not None:
            _RegDialog(self, "Okuma Register'ını düzenle", self.rm.extra_read[i], None, self._store_read)

    def del_read(self):
        i = self._sel(self.tv_x)
        if i is not None:
            del self.rm.extra_read[i]; self._refresh_read()

    # ------------------------------------------------------------- TX Register'ları
    def _tab_tx(self, nb):
        t = ttk.Frame(nb, padding=8); nb.add(t, text="TX ve kontrol Register'ları")
        ttk.Label(t, text="TX Config, TX Canlı Kontrol, IP reset ve RX read mode adresleri (hex). Boş bırakılan Register'a yazma yapılmaz.",
                  foreground="gray").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.txv = {}
        for r, (key, text) in enumerate(TX_REGISTERS, 1):
            ttk.Label(t, text=text).grid(row=r, column=0, sticky="w", padx=(0, 12), pady=2)
            self.txv[key] = tk.StringVar()
            ttk.Entry(t, textvariable=self.txv[key], width=8).grid(row=r, column=1, sticky="w")

    # ------------------------------------------------------------- yükle / uygula
    def load(self, ls=None):
        ls, rm = ls or self.app.ls, self.rm
        self._loading = True                # alanlar tek tek dolarken haritanın üzerine yazılmasın
        for k, var in self.cmd.items():
            var.set(getattr(rm, k))
        self.endian.set("Big Endian" if rm.endian == "big" else "Little Endian")
        self._loading = False
        for key, var in self.rv.items():
            var.set(str(_get(ls, key)))
        for key, var in self.txv.items():
            var.set(rm.tx_regs.get(key, ""))
        self._cmd_changed(); self._refresh_read()

    def reset(self):
        self.rm = RegisterMap(); self.load(LinkSettings())

    def apply(self):
        rm = self.rm
        try:
            rm.validate()
            limit = 1 << (8 * rm.addr_bytes())
            values = {}
            for key, var in self.rv.items():
                if key in DECIMAL_FIELDS:
                    v = int(var.get())
                    if v < 1:
                        raise ValueError(f"Derinlik değeri geçersiz: {v}")
                    values[key] = v
                else:
                    values[key] = norm_addr(var.get())
            tx = {k: (norm_addr(v.get()) if v.get().strip() else "") for k, v in self.txv.items()}
            used = [a for a in tx.values() if a]
            if len(set(used)) != len(used):
                raise ValueError("TX Register adresleri birbirinden farklı olmalı.")
            clash = sorted(set(used) & {r.addr for r in rm.write_regs})
            if clash:
                raise ValueError(f"{clash[0]} adresi hem TX hem Yazma Register'ı olarak kullanılıyor.")
            for a in used + [r.addr for r in rm.write_regs + rm.extra_read] + [v for k, v in values.items() if k not in DECIMAL_FIELDS]:
                if int(a, 16) >= limit:
                    raise ValueError(f"{a} adresi {{REG}} alanına sığmıyor.")
        except ValueError as e:
            messagebox.showerror("Komut ve Register Düzenleyici",
                                 str(e) if "base" not in str(e) else "Adres ve derinlik alanlarını kontrol edin.", parent=self)
            return False
        ls = self.app.ls
        for key, val in values.items():
            if isinstance(key, tuple):
                getattr(ls, key[0])[key[1]] = val
            else:
                setattr(ls, key, val)
        rm.tx_regs = tx
        self.app.ci.regmap = rm
        self.app.mark_dirty(); self.app.recalc(); self.destroy()
        return True
