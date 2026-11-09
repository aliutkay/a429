"""TX Canlı Kontrol penceresi: Word, Scheduler veya manuel gönderim ve hat override."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk, messagebox

from .txlive import (OVERRIDE_CODES, TIME_UNITS, build_word, fmt_binary, gap_from_period, parse_bin_word, parse_builder,
                     parse_hex_word, parity_bit, to_clk, word_fields_text)

OK_COLOR, BAD_COLOR = "#006100", "#C00000"
PLAY, PAUSE = "▶ Başlat", "⏸ Durdur"


class TxLiveWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("TX Canlı Kontrol"); self.resizable(False, False)
        self.configure(background=ttk.Style(self).lookup("TFrame", "background"))
        self.vars = {k: tk.StringVar() for k in app.ci.tx_live}
        self._loading = False
        self.manual_running, self.manual_after, self.sent, self.skipped = False, None, 0, 0
        body = ttk.Frame(self, padding=10); body.pack(fill=tk.BOTH, expand=True)
        self._build_word(body); self._build_send(body); self._build_override(body)
        ttk.Label(body, text="Bu pencere ortak Komut ve Register Düzenleyici'deki TX Register adreslerini kullanır.",
                  foreground="gray").pack(anchor="w", pady=(6, 0))
        for var in self.vars.values():
            var.trace_add("write", lambda *a: self._changed())
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.load()

    def close(self):
        self.stop_manual()
        self.destroy()

    # ------------------------------------------------------------- Word
    def _build_word(self, body):
        self.word_box = g = ttk.LabelFrame(body, text="Word", padding=8); g.pack(fill=tk.X)
        src = ttk.Frame(g); src.pack(fill=tk.X)
        ttk.Radiobutton(src, text="Word oluşturucu (alanları ayrı Register'lara yazar)", variable=self.vars["source"], value="builder").pack(anchor="w")
        ttk.Radiobutton(src, text="Direkt 32-bit Word", variable=self.vars["source"], value="direct").pack(anchor="w")

        self.builder = f = ttk.Frame(g)
        for r, (key, text) in enumerate((("label", "Label (octal)"), ("sdi", "SDI (0–3)"), ("data", "Data (hex, 19 bit)"), ("ssm", "SSM (0–3)"))):
            ttk.Label(f, text=text).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=2)
            ttk.Entry(f, textvariable=self.vars[key], width=12).grid(row=r, column=1, sticky="w")
        ttk.Label(f, text="Parity tipi").grid(row=4, column=0, sticky="w", padx=(0, 10), pady=2)
        ttk.Combobox(f, textvariable=self.vars["parity"], values=["Odd", "Even"], width=10, state="readonly").grid(row=4, column=1, sticky="w")

        self.direct = f = ttk.Frame(g)
        self.hex_var, self.bin_var = tk.StringVar(), tk.StringVar()
        ttk.Label(f, text="Hex").grid(row=0, column=0, sticky="w", padx=(0, 10), pady=2)
        ttk.Entry(f, textvariable=self.hex_var, width=12).grid(row=0, column=1, sticky="w")
        ttk.Label(f, text="Binary").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=2)
        ttk.Entry(f, textvariable=self.bin_var, width=42).grid(row=1, column=1, sticky="w")
        self.hex_var.trace_add("write", lambda *a: self._direct_edit("hex"))
        self.bin_var.trace_add("write", lambda *a: self._direct_edit("bin"))

        self.out = f = ttk.Frame(g); f.pack(fill=tk.X, pady=(6, 0))
        self.word_out, self.bin_out = tk.StringVar(), tk.StringVar()
        for r, (text, var, width) in enumerate((("Word (hex)", self.word_out, 12), ("Binary (P SSM Data SDI Label)", self.bin_out, 42))):
            ttk.Label(f, text=text).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=2)
            ttk.Entry(f, textvariable=var, width=width, state="readonly").grid(row=r, column=1, sticky="w")
            ttk.Button(f, text="Kopyala", width=8, command=lambda v=var: self.copy(v)).grid(row=r, column=2, padx=(6, 0))
        self.word_info = ttk.Label(g, text="", justify=tk.LEFT); self.word_info.pack(anchor="w", pady=(4, 2))
        ttk.Button(g, text="Word'ü IP'ye yaz", command=self.write_word).pack(anchor="w")

    def copy(self, var):
        if var.get():
            self.clipboard_clear(); self.clipboard_append(var.get().replace(" ", ""))
            self.app.status.set(f"Kopyalandı: {var.get()}")

    def _direct_edit(self, kind):
        if self._loading:
            return
        self._loading = True
        try:
            word = parse_hex_word(self.hex_var.get()) if kind == "hex" else parse_bin_word(self.bin_var.get())
            if kind == "hex":
                self.bin_var.set(fmt_binary(word))
            else:
                self.hex_var.set(f"{word:08X}")
            self.vars["word"].set(f"{word:08X}")
        except ValueError:
            pass
        self._loading = False
        self._changed()

    def current_word(self):
        cfg = {k: v.get() for k, v in self.vars.items()}
        if cfg["source"] == "builder":
            return build_word(*parse_builder(cfg))
        if self.bin_var.get().replace(" ", "") != f"{parse_hex_word(self.hex_var.get()):032b}":
            parse_bin_word(self.bin_var.get())
        return parse_hex_word(self.hex_var.get())

    def word_writes(self):
        cfg = {k: v.get() for k, v in self.vars.items()}
        if cfg["source"] == "direct":
            return [("tx_mode", 1), ("tx_word", self.current_word())]
        label, sdi, data, ssm, odd = parse_builder(cfg)
        build_word(label, sdi, data, ssm, odd)
        return [("tx_mode", 0), ("tx_label", label), ("tx_sdi", sdi), ("tx_data", data), ("tx_ssm", ssm), ("tx_parity_type", int(odd))]

    def write_word(self):
        try:
            writes = self.word_writes()
        except ValueError as e:
            messagebox.showerror("TX Canlı Kontrol", str(e), parent=self); return
        self.app.tx_write("TX Word yazılıyor", writes, parent=self)

    # ------------------------------------------------------------- gönderim
    def _time_row(self, f, r, text, key, unit_key):
        lbl = ttk.Label(f, text=text); lbl.grid(row=r, column=0, sticky="w", padx=(0, 10), pady=2)
        ent = ttk.Entry(f, textvariable=self.vars[key], width=12); ent.grid(row=r, column=1, sticky="w")
        cb = ttk.Combobox(f, textvariable=self.vars[unit_key], values=TIME_UNITS, width=5, state="readonly"); cb.grid(row=r, column=2, sticky="w", padx=(4, 0))
        return (lbl, ent, cb)

    def _build_send(self, body):
        self.send_box = g = ttk.LabelFrame(body, text="Gönderim", padding=8); g.pack(fill=tk.X, pady=(6, 0))
        modes = ttk.Frame(g); modes.pack(fill=tk.X)
        self.mode_radios = [ttk.Radiobutton(modes, text=t, variable=self.vars["send_mode"], value=v)
                            for t, v in (("Scheduler (IP otomatik gönderir)", "scheduler"), ("Manuel gönder", "manual"))]
        for r in self.mode_radios:
            r.pack(side=tk.LEFT, padx=(0, 12))

        self.sched_frame = s = ttk.Frame(g)
        self.sched_en = tk.BooleanVar(value=getattr(self.app, "tx_sched_on", False))
        f = ttk.Frame(s); f.pack(fill=tk.X)
        self._time_row(f, 0, "Internal delay", "delay_us", "delay_unit")
        ttk.Label(f, text="Interword gap").grid(row=1, column=0, sticky="w", padx=(0, 10), pady=2)
        m = ttk.Frame(f); m.grid(row=1, column=1, columnspan=2, sticky="w")
        ttk.Radiobutton(m, text="Periyottan hesapla", variable=self.vars["gap_mode"], value="period").pack(side=tk.LEFT)
        ttk.Radiobutton(m, text="Direkt gir", variable=self.vars["gap_mode"], value="direct").pack(side=tk.LEFT, padx=(8, 0))
        self.period_row = self._time_row(f, 2, "Periyot", "period_us", "period_unit")
        self.gap_row = self._time_row(f, 3, "Interword gap", "gap_us", "gap_unit")
        self.period_ent, self.gap_ent = self.period_row[1], self.gap_row[1]
        self.sched_info = ttk.Label(s, text="", justify=tk.LEFT, wraplength=620); self.sched_info.pack(anchor="w", pady=(4, 2))
        bar = ttk.Frame(s); bar.pack(fill=tk.X)
        self.sched_btn = ttk.Button(bar, text=PLAY, width=11, command=self.press_scheduler); self.sched_btn.pack(side=tk.LEFT)
        ttk.Button(bar, text="Scheduler ayarlarını yaz", command=self.write_scheduler).pack(side=tk.LEFT, padx=6)
        ttk.Label(s, text="Durdurulunca IP'deki clock sıfırlanır.", foreground="gray").pack(anchor="w", pady=(4, 0))

        self.manual_frame = m = ttk.Frame(g)
        f = ttk.Frame(m); f.pack(fill=tk.X)
        self._time_row(f, 0, "Periyot", "manual_period", "manual_unit")
        self.manual_info = ttk.Label(m, text="", justify=tk.LEFT); self.manual_info.pack(anchor="w", pady=(4, 2))
        bar = ttk.Frame(m); bar.pack(fill=tk.X)
        self.manual_play = ttk.Button(bar, text=PLAY, width=11, command=self.press_manual); self.manual_play.pack(side=tk.LEFT)
        self.manual_btn = ttk.Button(bar, text="Tek gönder", command=self.manual_send); self.manual_btn.pack(side=tk.LEFT, padx=6)
        ttk.Label(m, text="Periyodik gönderimi bilgisayar zamanlar; süre tutarlı olmayabilir.", foreground="gray").pack(anchor="w", pady=(4, 0))

    def _tbit_us(self):
        rate = self.app._current("tx_profile").rate_nom
        if rate <= 0:
            raise ValueError("TX ARINC profilinde Bit Rate NOM sıfırdan büyük olmalı.")
        return 1000 / rate

    @staticmethod
    def _number(text, name):
        try:
            value = float(text.replace(",", "."))
        except ValueError:
            raise ValueError(f"{name} sayı olmalı.") from None
        if value < 0:
            raise ValueError(f"{name} negatif olamaz.")
        return value

    def sched_values(self):
        """(delay_clk, gap_clk, açıklama)"""
        cfg = {k: v.get() for k, v in self.vars.items()}
        mhz = self.app.ci.clk_mhz
        delay_clk = round(to_clk(self._number(cfg["delay_us"], "Internal delay"), cfg["delay_unit"], mhz))
        if cfg["gap_mode"] == "period":
            period_us = to_clk(self._number(cfg["period_us"], "Periyot"), cfg["period_unit"], mhz) / mhz
            gap, word, fixed = gap_from_period(period_us, self._tbit_us())
            head = (f"TX profili: {self.app._current('tx_profile').name}\n"
                    f"Periyot: {period_us:g} µs\n"
                    f"Word süresi (32 Bit): {word:g} µs\n"
                    f"Zorunlu gap (4 Bit): {fixed:g} µs\n"
                    f"Interword gap = {period_us:g} − {word:g} − {fixed:g} = {gap:g} µs")
            if gap < 0:
                raise ValueError(head + "\nPeriyot çok kısa.")
            gap_clk = round(gap * mhz)
            text = f"{head} = {gap_clk:,} clk"
        else:
            gap_clk = round(to_clk(self._number(cfg["gap_us"], "Interword gap"), cfg["gap_unit"], mhz))
            text = f"Interword gap: {gap_clk / mhz:g} µs = {gap_clk:,} clk"
        return delay_clk, gap_clk, f"{text}\nInternal delay: {delay_clk / mhz:g} µs = {delay_clk:,} clk"

    def sched_writes(self):
        delay, gap, _ = self.sched_values()
        return [("sched_delay", delay), ("sched_gap", gap)]

    def write_scheduler(self):
        try:
            writes = self.sched_writes()
        except ValueError as e:
            messagebox.showerror("TX Canlı Kontrol", str(e), parent=self); return
        self.app.tx_write("TX Scheduler ayarları yazılıyor", writes, parent=self)

    def press_scheduler(self):
        self.sched_en.set(not self.sched_en.get())
        self.toggle_scheduler()

    def toggle_scheduler(self):
        enable = self.sched_en.get()

        def revert():
            if self.winfo_exists():
                self.sched_en.set(not enable); self._run_state()
            else:
                self.app.tx_sched_on = not enable
        try:
            writes = (self.sched_writes() + [("sched_enable", 1)]) if enable else [("sched_enable", 0)]
        except ValueError as e:
            messagebox.showerror("TX Canlı Kontrol", str(e), parent=self); revert(); return
        self._run_state()
        if not self.app.tx_write("TX Scheduler " + ("başlatılıyor" if enable else "durduruluyor"), writes, parent=self,
                                 on_done=lambda ok: None if ok else revert()):
            revert()

    def manual_period_ms(self):
        cfg = {k: v.get() for k, v in self.vars.items()}
        mhz = self.app.ci.clk_mhz
        ms = to_clk(self._number(cfg["manual_period"], "Periyot"), cfg["manual_unit"], mhz) / mhz / 1000
        if ms < 1:
            raise ValueError("Bilgisayarla periyodik gönderimde periyot en az 1 ms olmalı.")
        return ms

    def manual_send(self):
        self.app.tx_write("TX manuel gönderim", [("tx_manual_send", 1)], parent=self)

    def press_manual(self):
        if self.manual_running:
            self.stop_manual(); return
        try:
            self.manual_period_ms()
        except ValueError as e:
            messagebox.showerror("TX Canlı Kontrol", str(e), parent=self); return
        self.manual_running, self.sent, self.skipped = True, 0, 0
        self._run_state()
        self._tick()

    def _tick(self):
        if not self.manual_running:
            return
        try:
            ms = self.manual_period_ms()
        except ValueError:
            self.stop_manual(); return
        if self.app.busy:
            self.skipped += 1
        elif not self.app.tx_write("TX periyodik gönderim", [("tx_manual_send", 1)], parent=self, on_done=self._tick_done, quiet=True):
            self.stop_manual(); return
        self.manual_after = self.after(max(1, round(ms)), self._tick)
        self._manual_text()

    def _tick_done(self, ok):
        if not self.winfo_exists():
            return
        if ok:
            self.sent += 1; self._manual_text()
        else:
            self.stop_manual()

    def stop_manual(self):
        self.manual_running = False
        if self.manual_after:
            self.after_cancel(self.manual_after); self.manual_after = None
        if self.winfo_exists():
            self._run_state()

    def _manual_text(self):
        try:
            text = f"Periyot = {self.manual_period_ms():g} ms"
            color = "black"
        except ValueError as e:
            text, color = str(e), BAD_COLOR
        if self.sent or self.skipped or self.manual_running:
            text += f"  ·  Gönderilen: {self.sent}, atlanan: {self.skipped}"
        self.manual_info.configure(text=text, foreground="gray" if self.override_on() else color)

    def _run_state(self):
        on = self.sched_en.get()
        self.app.tx_sched_on = on
        self.sched_btn.configure(text=PAUSE if on else PLAY)
        self.manual_play.configure(text=PAUSE if self.manual_running else PLAY)
        self.manual_btn.configure(state=tk.DISABLED if self.manual_running else tk.NORMAL)
        running = on or self.manual_running
        for r in self.mode_radios:
            r.configure(state=tk.DISABLED if running else tk.NORMAL)
        if self.override_on():
            self._set_boxes_disabled(True)

    # ------------------------------------------------------------- hat override
    def _build_override(self, body):
        g = ttk.LabelFrame(body, text="Hat override", padding=8); g.pack(fill=tk.X, pady=(6, 0))
        self.override = tk.StringVar(value=getattr(self.app, "tx_override", "Kapalı"))
        top = ttk.Frame(g); top.pack(fill=tk.X)
        f = ttk.Frame(top); f.pack(side=tk.LEFT)
        for name in OVERRIDE_CODES:
            ttk.Radiobutton(f, text=name, variable=self.override, value=name).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(top, text="Uygula", command=self.apply_override).pack(side=tk.LEFT, padx=(8, 0))
        self.override_info = ttk.Label(g, text="", foreground=BAD_COLOR); self.override_info.pack(anchor="w", pady=(4, 0))

    def apply_override(self):
        choice = self.override.get()

        def done(ok):
            if ok:
                self.app.tx_override = choice
                if self.winfo_exists():
                    self._override_look()
        self.app.tx_write(f"TX hat override: {choice}", [("line_override", OVERRIDE_CODES[choice])], parent=self, on_done=done)

    def override_on(self):
        return getattr(self.app, "tx_override", "Kapalı") != "Kapalı"

    def _set_boxes_disabled(self, disabled):
        def walk(w):
            yield w
            for c in w.winfo_children():
                yield from walk(c)
        flag = ["disabled"] if disabled else ["!disabled"]
        for box in (self.word_box, self.send_box):
            for w in walk(box):
                if isinstance(w, ttk.Widget):
                    w.state(flag)

    def _override_look(self):
        on = self.override_on()
        if on:
            self.stop_manual()
        else:
            self._set_boxes_disabled(False)
        self._run_state()
        self.override_info.configure(text=f"Hat override etkin: {self.app.tx_override}. Word ve Gönderim kapatıldı; devam etmek için Kapalı seçip Uygula'ya basın." if on else "")
        self.refresh()

    # ------------------------------------------------------------- durum
    def load(self):
        self._loading = True
        cfg = self.app.ci.tx_live
        for k, var in self.vars.items():
            var.set(cfg[k])
        try:
            word = parse_hex_word(cfg["word"])
            self.hex_var.set(f"{word:08X}"); self.bin_var.set(fmt_binary(word))
        except ValueError:
            self.hex_var.set(cfg["word"])
        self._loading = False
        self._override_look()

    def _changed(self):
        if self._loading:
            return
        self.app.ci.tx_live.update({k: v.get() for k, v in self.vars.items()})
        self.app.mark_dirty()
        self.refresh()

    def refresh(self):
        direct = self.vars["source"].get() == "direct"
        self.builder.pack_forget(); self.direct.pack_forget()
        (self.direct if direct else self.builder).pack(fill=tk.X, pady=(6, 0), before=self.out)
        try:
            word = self.current_word()
            self.word_out.set(f"{word:08X}"); self.bin_out.set(fmt_binary(word))
            info = word_fields_text(word)
            info = (f"Hesaplanan Parity biti: {word >> 31}\n" + info if not direct
                    else info + f"\nParity tipi: {'Odd' if parity_bit(word, True) == word >> 31 else 'Even'}")
            self.word_info.configure(text=info, foreground="gray" if self.override_on() else "black")
        except ValueError as e:
            self.word_out.set(""); self.bin_out.set("")
            self.word_info.configure(text=str(e), foreground=BAD_COLOR)
        by_scheduler = self.vars["send_mode"].get() == "scheduler"
        self.sched_frame.pack_forget(); self.manual_frame.pack_forget()
        (self.sched_frame if by_scheduler else self.manual_frame).pack(fill=tk.X, pady=(6, 0))
        by_period = self.vars["gap_mode"].get() == "period"
        for row, show in ((self.period_row, by_period), (self.gap_row, not by_period)):
            for w in row:
                w.grid() if show else w.grid_remove()
        try:
            self.sched_info.configure(text=self.sched_values()[2], foreground="gray" if self.override_on() else OK_COLOR)
        except ValueError as e:
            self.sched_info.configure(text=str(e), foreground=BAD_COLOR)
        self._manual_text()
