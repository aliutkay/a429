"""RX Okunan Veriler sekmesi: Word Listesi, Dalga Formu, Bit Diagnostic, Error Listesi, İstatistik."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QHBoxLayout, QLabel, QLineEdit, QTabWidget, QVBoxLayout, QWidget,
)

from ..charts import draw_word
from ..decode import (
    Limits, bits_by_word, decode_bits, decode_errors, decode_words, ft, session_mhz, stats,
)
from ..regs import channel_label
from . import look
from .celltable import Cell, CellTable
from .config_tab import _fill_table, _make_table
from .figpanel import FigPanel, TIME_UNITS


class ReadTab(QWidget):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._clk_sync = False
        self._syncing = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(6)

        # Üst çubuk
        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(QLabel("Okuma:"))
        self.cb_sess = QComboBox()
        self.cb_sess.setMinimumWidth(240)
        self.cb_sess.currentTextChanged.connect(self._on_sess_selected)
        bar.addWidget(self.cb_sess)

        self.ch_pill = look.Pill("")
        bar.addWidget(self.ch_pill)

        bar.addWidget(look.button("Aç…", None, app.open_read))
        bar.addWidget(look.button("Yeniden adlandır", None, app.rename_session))
        bar.addWidget(look.button("Projeden çıkar", None, app.delete_session))
        bar.addSpacing(10)

        bar.addWidget(QLabel("Parity:"))
        self.cb_par = QComboBox()
        self.cb_par.addItems(["Odd Parity", "Even Parity"])
        self.cb_par.currentTextChanged.connect(lambda _: self.refresh())
        bar.addWidget(self.cb_par)

        bar.addWidget(QLabel("Timestamp tol. (%):"))
        self.ed_tol = QLineEdit("1")
        self.ed_tol.setFixedWidth(50)
        self.ed_tol.textChanged.connect(lambda _: self.refresh())
        bar.addWidget(self.ed_tol)

        bar.addWidget(QLabel("Veri clock'u (MHz):"))
        self.ed_clk = QLineEdit()
        self.ed_clk.setFixedWidth(72)
        self.ed_clk.textChanged.connect(self._on_data_clock_changed)
        bar.addWidget(self.ed_clk)

        bar.addWidget(look.label("Limitler güncel Config'den alınır", "muted"))
        bar.addStretch(1)
        lay.addLayout(bar)

        # Alt sekmeler
        self.sub = QTabWidget()
        self.sub.setDocumentMode(True)
        lay.addWidget(look.wrap_tabs(self.sub, "SubCard"), 1)

        def make_unit_bar(default: str):
            w = QWidget()
            hb = QHBoxLayout(w)
            hb.setContentsMargins(0, 2, 0, 2)
            hb.addWidget(QLabel("Zaman birimi:"))
            cb = QComboBox()
            cb.addItems(TIME_UNITS + ["s"])
            cb.setCurrentText(default)
            cb.currentTextChanged.connect(lambda _: self.refresh())
            hb.addWidget(cb)
            hb.addStretch(1)
            return w, cb

        # 1. Word Listesi
        w_page = QWidget()
        wl = QVBoxLayout(w_page)
        wl.setContentsMargins(6, 6, 6, 6)
        ub, self.u_word = make_unit_bar("µs")
        wl.addWidget(ub)
        self.tv_word = CellTable(
            [
                "Word No", "Timestamp", "Önceki Word'den geçen süre", "Label (octal)", "SDI",
                "Data (hex)", "SSM", "Parity", "Word Gap", "Gap Glitch Error",
                "ARINC Word (alım sırası)", "Min Pulse", "Max Pulse", "Min Bit", "Max Bit",
                "Toplam Pulse Glitch Error", "Toplam Null Glitch Error", "FAIL Bit sayısı",
                "32 Bit toplam süre", "32 Bit + Word Gap", "Timestamp farkı", "Süre farkı",
            ],
            [62, 110, 165, 85, 42, 75, 42, 55, 90, 110, 255, 80, 80, 80, 80, 155, 150, 95, 115, 120, 110, 90],
            on_double=self._word_to_wave,
        )
        wl.addWidget(self.tv_word, 1)
        wl.addWidget(look.label(
            "En yeni Word en üsttedir. Dalga formunu açmak için satıra çift tıklayın. Yeşil: PASS, kırmızı: FAIL. "
            "Nedenini görmek için hücrenin üzerine gelin veya sağ tıklayın.",
            "muted",
        ))
        self.sub.addTab(w_page, "Word Listesi")

        # 2. Word Dalga Formu
        wv_page = QWidget()
        wvl = QVBoxLayout(wv_page)
        wvl.setContentsMargins(6, 6, 6, 6)
        wbar = QHBoxLayout()
        wbar.addWidget(QLabel("Word No:"))
        self.cb_wword = QComboBox()
        self.cb_wword.setFixedWidth(90)
        self.cb_wword.currentTextChanged.connect(lambda _: self.draw_wave())
        wbar.addWidget(self.cb_wword)

        self.chk_wall = QCheckBox("Tüm Word'ler (Bit Diagnostic olmayanlar nominal çizilir)")
        self.chk_wall.toggled.connect(lambda _: self.refresh_wave_list())
        wbar.addWidget(self.chk_wall)

        wbar.addWidget(QLabel("Birim:"))
        self.u_wave = QComboBox()
        self.u_wave.addItems(TIME_UNITS)
        self.u_wave.currentTextChanged.connect(lambda _: self.draw_wave())
        wbar.addWidget(self.u_wave)

        wbar.addWidget(QLabel("Timestamp anı:"))
        self.cb_wts = QComboBox()
        self.cb_wts.addItems(["Word başı", "Word sonu"])
        self.cb_wts.currentTextChanged.connect(lambda _: self.draw_wave())
        wbar.addWidget(self.cb_wts)

        self.fmt_cbs: dict[str, QComboBox] = {}
        for key, lab, vals in (
            ("label_fmt", "Label", ["oct", "hex", "dec"]),
            ("sdi_fmt", "SDI", ["dec", "hex"]),
            ("data_fmt", "Data", ["hex", "dec", "oct"]),
            ("ssm_fmt", "SSM", ["dec", "hex"]),
        ):
            wbar.addWidget(QLabel(f"{lab}:"))
            cb = QComboBox()
            cb.addItems(vals)
            cb.setFixedWidth(62)
            cb.currentTextChanged.connect(lambda _: self.draw_wave())
            wbar.addWidget(cb)
            self.fmt_cbs[key] = cb
        wbar.addStretch(1)
        wvl.addLayout(wbar)

        self.fp_wave = FigPanel(self, (22, 7))
        wvl.addWidget(self.fp_wave, 1)
        self.sub.addTab(wv_page, "Word Dalga Formu")

        # 3. Bit Diagnostic
        b_page = QWidget()
        bl = QVBoxLayout(b_page)
        bl.setContentsMargins(6, 6, 6, 6)
        ub, self.u_bit = make_unit_bar("µs")
        bl.addWidget(ub)
        bl.addWidget(look.label("Yeşil: PASS, kırmızı: FAIL. Nedenini görmek için hücrenin üzerine gelin veya sağ tıklayın.", "muted"))
        self.tv_bit = CellTable(
            ["Word No", "Bit No (ARINC)", "Pulse", "Null", "Bit Time (Pulse + Null)",
             "Pulse Glitch Error", "Null Glitch Error", "Ham Register değerleri (hex)"],
            [62, 100, 90, 90, 150, 120, 115, 300],
        )
        bl.addWidget(self.tv_bit, 1)
        self.sub.addTab(b_page, "Bit Diagnostic")

        # 4. Error Listesi
        e_page = QWidget()
        el = QVBoxLayout(e_page)
        el.setContentsMargins(6, 6, 6, 6)
        ub, self.u_err = make_unit_bar("ms")
        el.addWidget(ub)
        el.addWidget(look.label("Yeşil: PASS, kırmızı: FAIL. Nedenini görmek için hücrenin üzerine gelin veya sağ tıklayın.", "muted"))
        self.tv_err = CellTable(
            ["No", "Timestamp", "Önceki Error'dan geçen süre", "Aktif Error'lar",
             "Error Address", "Error Data (hex)", "Error Data (decimal)"],
            [45, 110, 175, 320, 100, 115, 135],
        )
        el.addWidget(self.tv_err, 1)
        self.sub.addTab(e_page, "Error Listesi")

        # 5. İstatistik
        s_page = QWidget()
        sl = QVBoxLayout(s_page)
        sl.setContentsMargins(6, 6, 6, 6)
        sl.setSpacing(8)
        self.tv_st = _make_table(["Parametre", "Değer", "Açıklama"], [290, 160, 520])
        sl.addWidget(self.tv_st, 2)
        self.tv_stc = _make_table(["Tutarlılık kontrolü", "Sonuç"], [360, 140])
        sl.addWidget(self.tv_stc, 1)
        self.sub.addTab(s_page, "İstatistik")

    def load_settings(self):
        self._syncing = True
        ds = self.app.ds
        self.cb_par.setCurrentText("Odd Parity" if ds.parity_odd else "Even Parity")
        self.ed_tol.setText(f"{ds.ts_tol * 100:g}")
        self.cb_wts.setCurrentText("Word sonu" if ds.ts_at_word_end else "Word başı")
        for k, cb in self.fmt_cbs.items():
            cb.setCurrentText(getattr(ds, k))
        self._syncing = False

    def read_settings(self):
        ds = self.app.ds
        ds.parity_odd = self.cb_par.currentText().startswith("Odd")
        try:
            ds.ts_tol = float(self.ed_tol.text().strip().replace(",", ".")) / 100.0
        except ValueError:
            pass
        ds.ts_at_word_end = self.cb_wts.currentText() == "Word sonu"
        for k, cb in self.fmt_cbs.items():
            setattr(ds, k, cb.currentText())
        return ds

    def refresh_sessions(self):
        self._syncing = True
        self.cb_sess.blockSignals(True)
        self.cb_sess.clear()
        self.cb_sess.addItems([s["name"] for s in self.app.sessions])
        if self.app.cur_session:
            self.cb_sess.setCurrentText(self.app.cur_session["name"])
        self.cb_sess.blockSignals(False)
        self._syncing = False
        self.refresh()

    def _on_sess_selected(self, name: str):
        if self._syncing:
            return
        for s in self.app.sessions:
            if s["name"] == name:
                self.app.cur_session = s
                break
        self.refresh()

    def _show_data_clock(self, mhz):
        try:
            same = mhz is not None and float(self.ed_clk.text().strip().replace(",", ".")) == mhz
        except ValueError:
            same = False
        if not same:
            self._clk_sync = True
            self.ed_clk.setText("" if mhz is None else f"{mhz:g}")
            self._clk_sync = False

    def _on_data_clock_changed(self):
        if self._clk_sync or not self.app.cur_session:
            return
        try:
            mhz = float(self.ed_clk.text().strip().replace(",", "."))
            if mhz <= 0:
                raise ValueError
        except ValueError:
            self.app.set_status("Veri clock'u sıfırdan büyük bir sayı olmalı.")
            return
        self.app.cur_session["clk_mhz"] = mhz
        self.app.mark_dirty()
        self.refresh()

    def _limits(self, session):
        return Limits.from_result(self.app.res, self.app.ci.clk_mhz).for_clock(session_mhz(session, self.app.ci.clk_mhz))

    def refresh(self):
        if self._syncing or not self.app.res:
            return
        s = self.app.cur_session
        for tv in (self.tv_word, self.tv_bit, self.tv_err):
            tv.set_rows([])
        self.tv_st.setRowCount(0)
        self.tv_stc.setRowCount(0)
        if not s:
            self.ch_pill.set("")
            self._show_data_clock(None)
            self.refresh_wave_list()
            return

        ch = s.get("channel")
        self.ch_pill.set(channel_label(ch) if ch else "", "accent")

        lim = self._limits(s)
        ds = self.read_settings()
        mhz = session_mhz(s, self.app.ci.clk_mhz)
        self._show_data_clock(mhz)

        # Word Listesi
        u = self.u_word.currentText()
        T = lambda v: ft(v, u, mhz)
        par = "Odd" if ds.parity_odd else "Even"
        rows = []
        for r in decode_words(s, lim, ds):
            def chk(text, key, why):
                return Cell(text, r[key], why) if key in r else Cell(text)

            ones = bin(r["wd"]).count("1") if r.get("wd") is not None else 0
            fails = r.get("fail_list")
            rows.append([
                r["no"],
                chk(T(r["ts"]), "ts_order_ok", "Timestamp, önceki Word'den büyük olmalı."),
                T(r.get("dt")),
                f"{r['label']:03o}" if "label" in r else "?",
                r.get("sdi", ""),
                f"{r['data']:05X}" if "data" in r else "?",
                r.get("ssm", ""),
                chk(r.get("p", "?"), "parity_ok", f"{par} Parity bekleniyor; Word içindeki 1 sayısı: {ones}."),
                chk(T(r["gap"]), "gap_ok", f"Word Gap = {T(r['gap'])}, alt limit 4 × Min Bit = {T(4 * lim.minb)}."),
                chk(r["gerr"] if r["gerr"] is not None else "?", "gerr_ok", f"Gap Glitch Error = {r['gerr']}, limit ≤ {lim.gap_err}."),
                r.get("bin", ""),
                T(r.get("minp")), T(r.get("maxp")), T(r.get("minb")), T(r.get("maxb")),
                r.get("sum_perr", ""), r.get("sum_nerr", ""),
                Cell("") if fails is None else Cell(
                    len(fails), not fails,
                    "Limit dışı Bit yok." if not fails else "Limit dışı Bit'ler: " + ", ".join(map(str, fails)) + " (Bit Diagnostic sekmesi).",
                ),
                T(r.get("tot_bits")), T(r.get("bits_gap")), T(r.get("dts")),
                chk(
                    T(r.get("diff")), "ts_ok",
                    f"|Süre farkı| = {T(abs(r.get('diff') or 0))}, limit = %{ds.ts_tol * 100:g} × Timestamp farkı = {T(ds.ts_tol * (r.get('dts') or 0))}.",
                ),
            ])
        self.tv_word.set_rows(rows)

        # Bit Diagnostic
        u = self.u_bit.currentText()
        T = lambda v: ft(v, u, mhz)
        rows = []
        for r in decode_bits(s, lim):
            rows.append([
                r["word"], r["bit"] + 1,
                Cell(T(r["pulse"]), r["ok_pulse"], f"Pulse = {T(r['pulse'])}, limit {T(lim.minp)} … {T(lim.maxp)}."),
                T(r["null"]),
                Cell(T(r["bitlen"]), r["ok_bit"], f"Bit Time (Pulse + Null) = {T(r['bitlen'])}, limit {T(lim.minb)} … {T(lim.maxb)}."),
                Cell(r["perr"], r["ok_perr"], f"Pulse Glitch Error = {r['perr']}, limit ≤ {lim.pulse_err}."),
                Cell(r["nerr"], r["ok_nerr"], f"Null Glitch Error = {r['nerr']}, limit ≤ {lim.null_err}."),
                Cell(" ".join("XXXXXXXX" if x is None else f"{x:08X}" for x in r["raw"]), r["ok_pad"],
                     "Padding kontrolü: Pulse, Null ve Glitch Error değerleri 16 bit içinde olmalı."),
            ])
        self.tv_bit.set_rows(rows)

        # Error Listesi
        u = self.u_err.currentText()
        T = lambda v: ft(v, u, mhz)
        rows = []
        for i, r in enumerate(decode_errors(s)):
            rows.append([
                i + 1, T(r["ts"]), T(r["dt"]),
                Cell(r["active"], r["code_ok"] and not any(r["flags"]),
                     f"Aktif Error'lar: {r['active']}." if r["code_ok"] else "Error Code okunamadı."),
                Cell(r["addr"], r["pad_ok"], "Padding kontrolü: Error Code 16 bit, Error Address 16 bit içinde olmalı."),
                " ".join(f"{b:02X}" for b in (r["data"] or 0).to_bytes(4, "big")),
                r["data"],
            ])
        self.tv_err.set_rows(rows)

        # İstatistik
        wdepth = s.get("wdepth", 256)
        edepth = s.get("edepth", 256)
        bit_words = s.get("bit_words", 8)
        st_rows, st_chk = stats(s, lim, wdepth, edepth, bit_words)
        _fill_table(self.tv_st, [list(r) for r in st_rows])
        _fill_table(
            self.tv_stc,
            [list(c) for c in st_chk],
            ["fail" if c[1] == "FAIL" else ("ok" if c[1] == "PASS" else "") for c in st_chk],
        )
        self.refresh_wave_list()

    def refresh_wave_list(self):
        s = self.app.cur_session
        self.cb_wword.blockSignals(True)
        cur = self.cb_wword.currentText()
        self.cb_wword.clear()
        if not s:
            self.cb_wword.blockSignals(False)
            self.fp_wave.fig.clear()
            self.fp_wave.draw()
            return
        bm = bits_by_word(s)
        nos = [str(w["no"]) for w in s.get("words", []) if self.chk_wall.isChecked() or len(bm.get(w["no"], {})) >= 32]
        self.cb_wword.addItems(nos)
        if cur in nos:
            self.cb_wword.setCurrentText(cur)
        elif nos:
            self.cb_wword.setCurrentIndex(0)
        self.cb_wword.blockSignals(False)
        self.draw_wave()

    def _word_to_wave(self, row: int):
        no = self.tv_word.cell_text(row, 0)
        if self.cb_wword.findText(no) < 0:
            self.chk_wall.setChecked(True)
            self.refresh_wave_list()
        self.cb_wword.setCurrentText(no)
        self.sub.setCurrentIndex(1)

    def draw_wave(self):
        s = self.app.cur_session
        txt = self.cb_wword.currentText()
        if not s or not txt or not self.app.res:
            return
        no = int(txt)
        lim = self._limits(s)
        ds = self.read_settings()
        rows = {r["no"]: r for r in decode_words(s, lim, ds)}
        if no not in rows:
            return
        bm = bits_by_word(s).get(no, {})
        bmap = {b: ((v["w"][0] or 0), (v["w"][2] or 0)) for b, v in bm.items()}
        mhz = session_mhz(s, self.app.ci.clk_mhz)
        f = mhz / self.app.ci.clk_mhz
        nom = (round(self.app.res.nom_clk[0] * f), round(self.app.res.nom_clk[2] * f))
        try:
            draw_word(self.fp_wave.fig, rows[no], bmap, mhz, self.u_wave.currentText(), ds, nom)
            self.fp_wave.draw()
        except Exception as e:
            self.app.set_status(f"Dalga formu çizilemedi: {e}")
