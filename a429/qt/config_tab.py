"""Config sekmesi: Genel / RX Config / TX Config girişleri ve hesaplanan sonuçlar."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFrame, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QScrollArea, QSplitter, QTableWidget,
    QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget,
)

from ..formulas import DERIVED_ROWS
from . import look
from .dialogs import FormulaDialog


def _make_table(headers: list[str], widths: list[int]) -> QTableWidget:
    tv = QTableWidget(0, len(headers))
    tv.setHorizontalHeaderLabels(headers)
    tv.setAlternatingRowColors(True)
    tv.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tv.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    tv.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tv.verticalHeader().setVisible(False)
    tv.verticalHeader().setDefaultSectionSize(22)
    tv.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    tv.horizontalHeader().setStretchLastSection(True)
    for i, w in enumerate(widths):
        tv.setColumnWidth(i, w)
    return tv


def _fill_table(tv: QTableWidget, rows: list[list], states: list[str] | None = None, tips: list[str | None] | None = None):
    tv.setRowCount(len(rows))
    ok_fg = look.color("success")
    bad_fg = look.color("danger")
    for r, row in enumerate(rows):
        st = states[r] if states and r < len(states) else ""
        tip = tips[r] if tips and r < len(tips) else None
        for c, val in enumerate(row):
            it = QTableWidgetItem("" if val is None else str(val))
            it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | (Qt.AlignmentFlag.AlignLeft if c == 0 else Qt.AlignmentFlag.AlignCenter))
            if st == "ok":
                it.setForeground(QBrush(ok_fg))
            elif st == "fail":
                it.setForeground(QBrush(bad_fg))
            if tip:
                it.setToolTip(tip)
            tv.setItem(r, c, it)


class ConfigTab(QWidget):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._loading = False
        self._formula_dlg = None

        root = QHBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        # ---- Sol panel (ferah, kaydırılabilir)
        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setFrameShape(QFrame.Shape.NoFrame)
        left_scroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }")
        left_scroll.setMinimumWidth(380)
        left_scroll.setMaximumWidth(455)

        left = QWidget()
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 4, 0)
        llay.setSpacing(10)
        self._edit_btns = []

        def pencil(slot, tip: str):
            b = look.edit_button(slot, tip)
            self._edit_btns.append(b)
            return b

        # Genel (kompakt tek satırda iki giriş)
        g_gen = QGroupBox("Genel")
        gl = QGridLayout(g_gen)
        gl.setHorizontalSpacing(10)
        gl.setVerticalSpacing(4)
        gl.addWidget(look.label("System Clock (MHz)", "muted"), 0, 0)
        gl.addWidget(look.label("Tolerans (±ppm)", "muted"), 0, 1)
        self.ed_clk = QLineEdit()
        self.ed_clk.textChanged.connect(self._on_input)
        self.ed_ppm = QLineEdit()
        self.ed_ppm.textChanged.connect(self._on_input)
        gl.addWidget(self.ed_clk, 1, 0)
        gl.addWidget(self.ed_ppm, 1, 1)
        llay.addWidget(g_gen)

        # RX Config
        g_rx = QGroupBox("RX Config")
        gl = QGridLayout(g_rx)
        gl.setHorizontalSpacing(8)
        gl.setVerticalSpacing(7)
        gl.setColumnStretch(1, 1)

        gl.addWidget(QLabel("ARINC 429 profili"), 0, 0)
        self.cb_rx_prof = QComboBox()
        self.cb_rx_prof.currentTextChanged.connect(lambda t: self._on_profile("profile", t))
        gl.addWidget(self.cb_rx_prof, 0, 1)
        gl.addWidget(pencil(app.open_arinc_dialog, "ARINC 429 profillerini düzenle"), 0, 2)

        gl.addWidget(QLabel("Receiver entegresi"), 1, 0)
        self.cb_ic = QComboBox()
        self.cb_ic.currentTextChanged.connect(lambda t: self._on_profile("ic_profile", t))
        gl.addWidget(self.cb_ic, 1, 1)
        gl.addWidget(pencil(app.open_ic_dialog, "Receiver entegresini düzenle"), 1, 2)

        gl.addWidget(QLabel("FPGA giriş standardı"), 2, 0)
        self.cb_fpga = QComboBox()
        self.cb_fpga.currentTextChanged.connect(self._on_fpga)
        gl.addWidget(self.cb_fpga, 2, 1)
        gl.addWidget(pencil(app.open_fpga_dialog, "FPGA giriş standartlarını düzenle"), 2, 2)

        gl.addWidget(QLabel("Test toleransı (%)"), 3, 0)
        self.ed_err = QLineEdit()
        self.ed_err.setFixedWidth(90)
        self.ed_err.textChanged.connect(self._on_input)
        gl.addWidget(self.ed_err, 3, 1, Qt.AlignmentFlag.AlignLeft)

        # Glitch Filter & Limitler: temiz tam genişlikte özet kartı + sağda kalem
        gf_box = QFrame()
        gf_box.setObjectName("SubPanel")
        gfl = QVBoxLayout(gf_box)
        gfl.setContentsMargins(10, 7, 8, 7)
        gfl.setSpacing(3)
        gf_top = QHBoxLayout()
        gf_top.setSpacing(6)
        gf_top.addWidget(look.label("Glitch Filter:", "muted"))
        self.lbl_gf_val = look.label("", "cardTitle")
        gf_top.addWidget(self.lbl_gf_val)
        gf_top.addStretch(1)
        gf_top.addWidget(pencil(app.open_glitch_dialog, "Glitch Filter ve limitleri düzenle"))
        gfl.addLayout(gf_top)
        self.lbl_gf_lim = look.label("", "muted")
        gfl.addWidget(self.lbl_gf_lim)
        gl.addWidget(gf_box, 4, 0, 1, 3)

        for r, (kind, txt) in enumerate((("example", "Örnek dalga formu"), ("single", "Tek Bit analizi")), 5):
            gl.addWidget(QLabel(txt), r, 0)
            row = QHBoxLayout()
            row.setSpacing(5)
            for case in ("MIN", "NOM", "MAX"):
                row.addWidget(look.button(case, None, lambda _, k=kind, c=case: app.open_chart(k, c)), 1)
            gl.addLayout(row, r, 1, 1, 2)
        llay.addWidget(g_rx)

        # TX Config
        g_tx = QGroupBox("TX Config")
        gl = QGridLayout(g_tx)
        gl.setHorizontalSpacing(8)
        gl.setVerticalSpacing(7)
        gl.setColumnStretch(1, 1)

        gl.addWidget(QLabel("ARINC 429 profili"), 0, 0)
        self.cb_tx_prof = QComboBox()
        self.cb_tx_prof.currentTextChanged.connect(lambda t: self._on_profile("tx_profile", t))
        gl.addWidget(self.cb_tx_prof, 0, 1)
        gl.addWidget(pencil(app.open_arinc_dialog, "ARINC 429 profillerini düzenle"), 0, 2)

        gl.addWidget(QLabel("Line Driver entegresi"), 1, 0)
        self.cb_tx_drv = QComboBox()
        self.cb_tx_drv.currentTextChanged.connect(lambda t: self._on_profile("tx_driver", t))
        gl.addWidget(self.cb_tx_drv, 1, 1)
        gl.addWidget(pencil(app.open_tx_driver_dialog, "Line Driver entegresini düzenle"), 1, 2)

        gl.addWidget(QLabel("FPGA çıkış standardı"), 2, 0)
        self.cb_tx_fpga = QComboBox()
        self.cb_tx_fpga.currentTextChanged.connect(self._on_tx_fpga)
        gl.addWidget(self.cb_tx_fpga, 2, 1)
        gl.addWidget(pencil(app.open_tx_fpga_dialog, "FPGA çıkış standartlarını düzenle"), 2, 2)

        self.chk_tx_comp = QCheckBox("Gecikme telafisi (tPHL − tPLH)")
        self.chk_tx_comp.setToolTip("Line Driver nominal gecikme asimetrisini TX_CUST_PULSE_DUR / NULL_DUR'da telafi eder")
        self.chk_tx_comp.toggled.connect(self._on_tx_opt)
        gl.addWidget(self.chk_tx_comp, 3, 0, 1, 3)

        self.chk_tx_gap = QCheckBox("Word Gap ±ppm güvenlik marjı")
        self.chk_tx_gap.setToolTip("Clock hızlı sapmasında dahi Word Gap ≥ 4 Bit Time olsun diye yukarı yuvarlar")
        self.chk_tx_gap.toggled.connect(self._on_tx_opt)
        gl.addWidget(self.chk_tx_gap, 4, 0, 1, 3)

        for r, (kind, txt) in enumerate((("tx_example", "Örnek dalga formu"), ("tx_single", "Tek Bit analizi")), 5):
            gl.addWidget(QLabel(txt), r, 0)
            row = QHBoxLayout()
            row.setSpacing(5)
            for case in ("MIN", "NOM", "MAX"):
                row.addWidget(look.button(case, None, lambda _, k=kind, c=case: app.open_chart(k, c)), 1)
            gl.addLayout(row, r, 1, 1, 2)

        llay.addWidget(g_tx)
        llay.addStretch(1)

        left_scroll.setWidget(left)
        splitter.addWidget(left_scroll)

        # ---- Sağ panel (RX / TX sekmeleri)
        self.side_tabs = QTabWidget()
        self.side_tabs.setDocumentMode(True)
        splitter.addWidget(look.wrap_tabs(self.side_tabs, "SubCard"))
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([415, 1015])

        # RX alt sekmesi
        rx_page = QWidget()
        rlay = QVBoxLayout(rx_page)
        rlay.setContentsMargins(8, 8, 8, 8)
        rlay.setSpacing(8)
        self.lbl_rx_chk = look.label("", "cardTitle")
        rlay.addWidget(self.lbl_rx_chk)

        det = QTabWidget()
        det.setDocumentMode(True)
        chk_w = QWidget()
        chkl = QVBoxLayout(chk_w)
        chkl.setContentsMargins(6, 6, 6, 6)
        self.tv_chk = _make_table(["Kontrol", "Sonuç"], [480, 90])
        chkl.addWidget(self.tv_chk, 1)
        det.addTab(chk_w, "Kontroller")

        dur_w = QWidget()
        dlay = QVBoxLayout(dur_w)
        dlay.setContentsMargins(6, 6, 6, 6)
        self.tv_dur = _make_table(["Parametre", "µs", "clk"], [340, 100, 100])
        self.tv_dur.doubleClicked.connect(lambda idx: self._open_formula(self.tv_dur, idx.row(), ("µs", "clk")))
        dlay.addWidget(self.tv_dur, 1)
        dlay.addWidget(look.label("Formülü görmek için satıra çift tıklayın.", "muted"))
        det.addTab(dur_w, "Test toleransı eklenmiş süreler")

        mid_w = QWidget()
        mlay = QVBoxLayout(mid_w)
        mlay.setContentsMargins(6, 6, 6, 6)
        mlay.addWidget(look.label("Fiziksel en kötü durum, test toleransı eklenmemiş. Formülü görmek için satıra çift tıklayın.", "muted"))
        self.tv_mid = _make_table(["Parametre", "MIN", "NOM", "MAX"], [420, 90, 90, 90])
        self.tv_mid.doubleClicked.connect(lambda idx: self._open_formula(self.tv_mid, idx.row(), ("MIN", "NOM", "MAX")))
        mlay.addWidget(self.tv_mid, 1)
        det.addTab(mid_w, "Ara hesaplar ve formüller")
        rlay.addWidget(look.wrap_tabs(det, "SubCard"), 1)

        g_rregs = QGroupBox("RX Config Register'ları")
        grl = QVBoxLayout(g_rregs)
        self.tv_rx_regs = _make_table(
            ["Register", "Studio register adı", "Offset", "Değer", "Değer (hex)"],
            [220, 230, 85, 95, 120],
        )
        grl.addWidget(self.tv_rx_regs, 1)
        rbar = QHBoxLayout()
        rbar.addWidget(look.button("Değerleri panoya kopyala", None, self._copy_rx_values))
        self.btn_rx_add_cfg = look.button("Debug Bridge config listesine ekle", None, app.add_rx_to_bridge_config)
        rbar.addWidget(self.btn_rx_add_cfg)
        rbar.addStretch(1)
        grl.addLayout(rbar)
        rlay.addWidget(g_rregs, 1)
        self.side_tabs.addTab(rx_page, "RX")

        # TX alt sekmesi
        tx_page = QWidget()
        tlay = QVBoxLayout(tx_page)
        tlay.setContentsMargins(8, 8, 8, 8)
        tlay.setSpacing(8)
        self.lbl_tx_chk = look.label("", "cardTitle")
        tlay.addWidget(self.lbl_tx_chk)
        self.lbl_tx_info = look.label("", "muted", wrap=True)
        tlay.addWidget(self.lbl_tx_info)

        tdet = QTabWidget()
        tdet.setDocumentMode(True)
        tchk_w = QWidget()
        tchkl = QVBoxLayout(tchk_w)
        tchkl.setContentsMargins(6, 6, 6, 6)
        self.tv_tx_chk = _make_table(["Kontrol", "Sonuç"], [480, 90])
        tchkl.addWidget(self.tv_tx_chk, 1)
        tdet.addTab(tchk_w, "Kontroller")

        tmid_w = QWidget()
        tmidl = QVBoxLayout(tmid_w)
        tmidl.setContentsMargins(6, 6, 6, 6)
        tmidl.addWidget(look.label("FPGA çıkışı → Line Driver → ARINC 429 hattı fiziksel zamanlama ve genlik analizi.", "muted"))
        self.tv_tx_mid = _make_table(["Parametre", "MIN", "NOM", "MAX"], [420, 90, 90, 90])
        tmidl.addWidget(self.tv_tx_mid, 1)
        tdet.addTab(tmid_w, "Ara hesaplar")
        tlay.addWidget(look.wrap_tabs(tdet, "SubCard"), 1)

        g_tregs = QGroupBox("TX Config Register'ları")
        gtrl = QVBoxLayout(g_tregs)
        self.tv_tx_regs = _make_table(
            ["Register", "Studio register adı", "Offset", "Değer", "Değer (hex)"],
            [220, 210, 85, 95, 120],
        )
        gtrl.addWidget(self.tv_tx_regs, 1)
        tbar = QHBoxLayout()
        tbar.addWidget(look.button("Değerleri panoya kopyala", None, self._copy_tx_values))
        self.btn_tx_add_cfg = look.button("Debug Bridge config listesine ekle", None, app.add_tx_to_bridge_config)
        tbar.addWidget(self.btn_tx_add_cfg)
        tbar.addStretch(1)
        gtrl.addLayout(tbar)
        tlay.addWidget(g_tregs, 1)
        self.side_tabs.addTab(tx_page, "TX")

    def load_from_model(self):
        self._loading = True
        ci = self.app.ci
        self.ed_clk.setText(f"{ci.clk_mhz:g}")
        self.ed_ppm.setText(f"{ci.ppm:g}")
        self.ed_err.setText(f"{ci.err * 100:g}")
        self.chk_tx_comp.setChecked(ci.tx_comp_delay)
        self.chk_tx_gap.setChecked(ci.tx_gap_margin)
        self.refresh_combos()
        self._loading = False

    def refresh_combos(self):
        self._loading = True
        ci = self.app.ci
        for cb, items, cur in (
            (self.cb_rx_prof, [p.name for p in ci.profiles], ci.profile),
            (self.cb_tx_prof, [p.name for p in ci.profiles], ci.tx_profile),
            (self.cb_ic, [p.name for p in ci.ic_profiles], ci.ic.name),
            (self.cb_fpga, [r[0] for r in ci.fpga_table], ci.fpga_std),
            (self.cb_tx_drv, [d.name for d in ci.tx_drivers], ci.driver.name),
            (self.cb_tx_fpga, [r[0] for r in ci.tx_fpga_table], ci.tx_fpga_std),
        ):
            cb.blockSignals(True)
            cb.clear()
            cb.addItems(items)
            cb.setCurrentText(cur)
            cb.blockSignals(False)
        self._loading = False

    def read_to_model(self):
        ci = self.app.ci
        def num(ed: QLineEdit, name: str) -> float:
            try:
                v = float(ed.text().strip().replace(",", "."))
                ed.setProperty("bad", "false")
                look.repolish(ed)
                return v
            except ValueError:
                ed.setProperty("bad", "true")
                look.repolish(ed)
                raise ValueError(f"'{name}' alanı sayı olmalı.") from None

        ci.clk_mhz = num(self.ed_clk, "System Clock")
        ci.ppm = num(self.ed_ppm, "System Clock toleransı")
        ci.err = num(self.ed_err, "Test toleransı") / 100.0
        if self.cb_fpga.currentText():
            ci.fpga_std = self.cb_fpga.currentText()
        if self.cb_tx_fpga.currentText():
            ci.tx_fpga_std = self.cb_tx_fpga.currentText()
        ci.tx_comp_delay = self.chk_tx_comp.isChecked()
        ci.tx_gap_margin = self.chk_tx_gap.isChecked()

    def _on_input(self):
        if not self._loading:
            self.app.schedule_recalc()

    def _on_profile(self, key: str, name: str):
        if not self._loading and name:
            self.app.select_profile(key, name)

    def _on_fpga(self, name: str):
        if not self._loading and name:
            self.app.ci.fpga_std = name
            self.app.schedule_recalc()

    def _on_tx_fpga(self, name: str):
        if not self._loading and name:
            self.app.ci.tx_fpga_std = name
            self.app.schedule_recalc()

    def _on_tx_opt(self):
        if not self._loading:
            self.app.ci.tx_comp_delay = self.chk_tx_comp.isChecked()
            self.app.ci.tx_gap_margin = self.chk_tx_gap.isChecked()
            self.app.schedule_recalc()

    def restyle_icons(self):
        ic = look.pencil_icon()
        for b in self._edit_btns:
            b.setIcon(ic)

    def update_results(self, res, tx_res):
        ci = self.app.ci
        gf = f"%{ci.gf_ratio * 100:g} × {ci.gf_ref}" if ci.gf_mode == "ratio" else f"{ci.gf_clock} clock"
        self.lbl_gf_val.setText(gf)
        self.lbl_gf_lim.setText(
            f"MAX Glitch — Pulse: %{ci.pulse_glitch_pct * 100:g}  ·  "
            f"Null: %{ci.null_glitch_pct * 100:g}  ·  "
            f"Gap: %{ci.gap_glitch_pct * 100:g} ({ci.glitch_base})"
        )

        # RX tabloları
        if res is not None:
            _fill_table(
                self.tv_rx_regs,
                [[r[0], self.app.rm.field_label(r[1]), r[2], "" if r[3] is None else f"{r[3]:,}", r[4]] for r in res.regs],
                ["fail" if r[5] else "" for r in res.regs],
                [r[5] for r in res.regs],
            )
            fmt = lambda x: "" if x is None else f"{x:.3f}"
            _fill_table(self.tv_mid, [[k, fmt(a), fmt(b), fmt(c)] for k, (a, b, c) in res.rows.items()])
            _fill_table(
                self.tv_dur,
                [[k, f"{us:.3f}", f"{clk:,}"] for k, (us, clk) in res.dur.items()]
                + [[k, f"{res.vars[key] / ci.clk_mhz:.3f}", f"{res.vars[key]:,}"] for k, key in DERIVED_ROWS],
            )
            _fill_table(
                self.tv_chk,
                [[n, "OK" if ok else "UYARI"] for n, ok in res.checks],
                ["ok" if ok else "fail" for _, ok in res.checks],
            )
            bad = sum(1 for _, ok in res.checks if not ok)
            self.lbl_rx_chk.setText(
                f"UYARI: {bad} RX kontrolü sağlanmıyor (ayrıntı: Kontroller sekmesi)."
                if bad
                else f"Tüm RX kontrolleri sağlanıyor ({len(res.checks)}/{len(res.checks)})."
            )
            self.lbl_rx_chk.setStyleSheet(f"color: {look.tokens()['danger' if bad else 'success']};")

        # TX tabloları
        if tx_res is not None:
            _fill_table(
                self.tv_tx_regs,
                [[r[0], self.app.rm.field_label(r[1]), r[2], "" if r[3] is None else f"{r[3]:,}", r[4]] for r in tx_res["regs"]],
                ["fail" if r[5] else "" for r in tx_res["regs"]],
                [r[5] for r in tx_res["regs"]],
            )
            _fill_table(
                self.tv_tx_chk,
                [[n, "OK" if ok else "UYARI"] for n, ok in tx_res["checks"]],
                ["ok" if ok else "fail" for _, ok in tx_res["checks"]],
            )
            fmt = lambda x: "" if x is None else f"{x:.3f}"
            _fill_table(self.tv_tx_mid, [[k, fmt(a), fmt(b), fmt(c)] for k, (a, b, c) in tx_res.get("rows", {}).items()])
            bad = sum(1 for _, ok in tx_res["checks"] if not ok)
            self.lbl_tx_chk.setText(
                f"UYARI: {bad} TX kontrolü sağlanmıyor."
                if bad
                else f"Tüm TX kontrolleri sağlanıyor ({len(tx_res['checks'])}/{len(tx_res['checks'])})."
            )
            self.lbl_tx_chk.setStyleSheet(f"color: {look.tokens()['danger' if bad else 'success']};")
            self.lbl_tx_info.setText(tx_res["text"])
        else:
            self.tv_tx_regs.setRowCount(0)
            self.tv_tx_chk.setRowCount(0)
            self.tv_tx_mid.setRowCount(0)
            self.lbl_tx_chk.setText("TX Config hesaplanamadı.")
            self.lbl_tx_chk.setStyleSheet(f"color: {look.tokens()['danger']};")
            self.lbl_tx_info.setText("")

    def _open_formula(self, tv: QTableWidget, row: int, heads: tuple[str, ...]):
        if row < 0 or row >= tv.rowCount():
            return
        vals = [tv.item(row, c).text() if tv.item(row, c) else "" for c in range(tv.columnCount())]
        key = vals[0]
        if "gecikmesi" in key:
            heads = ("Min Pulse durumu", "NOM", "Max Pulse durumu")
        shown = " · ".join(f"{h} = {v}" for h, v in zip(heads, vals[1:]) if v != "")
        if self._formula_dlg is not None:
            self._formula_dlg.close()
        self._formula_dlg = FormulaDialog(self, key, shown)
        self._formula_dlg.show()

    def _copy_rx_values(self):
        if not self.app.res:
            return
        lines = [f"{r[1]}={r[4]}" for r in self.app.res.regs if r[3] is not None]
        QApplication.clipboard().setText("\n".join(lines))
        self.app.set_status("RX Config değerleri panoya kopyalandı.")

    def _copy_tx_values(self):
        if not self.app.res_tx:
            return
        lines = [f"{r[1]}={r[4]}" for r in self.app.res_tx["regs"] if r[3] is not None]
        QApplication.clipboard().setText("\n".join(lines))
        self.app.set_status("TX Config değerleri panoya kopyalandı.")
