"""Config sekmesi: Genel / RX Config / TX Config girişleri ve hesaplanan sonuçlar."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QGridLayout, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QSplitter, QTableWidget, QTableWidgetItem, QTabWidget,
    QVBoxLayout, QWidget,
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

        # ---- Sol panel
        left = QWidget()
        left.setMaximumWidth(420)
        llay = QVBoxLayout(left)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(8)

        # Genel
        g_gen = QGroupBox("Genel")
        gl = QGridLayout(g_gen)
        gl.addWidget(QLabel("System Clock (MHz)"), 0, 0)
        self.ed_clk = QLineEdit()
        self.ed_clk.setFixedWidth(90)
        self.ed_clk.textChanged.connect(self._on_input)
        gl.addWidget(self.ed_clk, 0, 1)
        gl.addWidget(QLabel("System Clock toleransı (±ppm)"), 1, 0)
        self.ed_ppm = QLineEdit()
        self.ed_ppm.setFixedWidth(90)
        self.ed_ppm.textChanged.connect(self._on_input)
        gl.addWidget(self.ed_ppm, 1, 1)
        llay.addWidget(g_gen)

        # RX Config
        g_rx = QGroupBox("RX Config")
        gl = QGridLayout(g_rx)
        gl.addWidget(QLabel("ARINC 429 profili"), 0, 0)
        self.cb_rx_prof = QComboBox()
        self.cb_rx_prof.currentTextChanged.connect(lambda t: self._on_profile("profile", t))
        gl.addWidget(self.cb_rx_prof, 0, 1)
        gl.addWidget(look.button("Düzenle…", None, app.open_arinc_dialog), 0, 2)

        gl.addWidget(QLabel("Receiver entegresi"), 1, 0)
        self.cb_ic = QComboBox()
        self.cb_ic.currentTextChanged.connect(lambda t: self._on_profile("ic_profile", t))
        gl.addWidget(self.cb_ic, 1, 1)
        gl.addWidget(look.button("Düzenle…", None, app.open_ic_dialog), 1, 2)

        gl.addWidget(QLabel("FPGA giriş standardı"), 2, 0)
        self.cb_fpga = QComboBox()
        self.cb_fpga.currentTextChanged.connect(self._on_fpga)
        gl.addWidget(self.cb_fpga, 2, 1)
        gl.addWidget(look.button("Düzenle…", None, app.open_fpga_dialog), 2, 2)

        gl.addWidget(QLabel("Glitch Filter ve limitler"), 3, 0)
        self.lbl_glitch = look.label("", "muted", wrap=True)
        gl.addWidget(self.lbl_glitch, 3, 1)
        gl.addWidget(look.button("Düzenle…", None, app.open_glitch_dialog), 3, 2)

        gl.addWidget(QLabel("Test toleransı (%)"), 4, 0)
        self.ed_err = QLineEdit()
        self.ed_err.setFixedWidth(90)
        self.ed_err.textChanged.connect(self._on_input)
        gl.addWidget(self.ed_err, 4, 1)

        for r, (kind, txt) in enumerate((("example", "Örnek dalga formu"), ("single", "Tek Bit analizi")), 5):
            gl.addWidget(QLabel(txt), r, 0)
            row = QHBoxLayout()
            row.setSpacing(4)
            for case in ("MIN", "NOM", "MAX"):
                row.addWidget(look.button(case, None, lambda _, k=kind, c=case: app.open_chart(k, c)))
            row.addStretch(1)
            gl.addLayout(row, r, 1, 1, 2)
        llay.addWidget(g_rx)

        # TX Config
        g_tx = QGroupBox("TX Config")
        gl = QGridLayout(g_tx)
        gl.addWidget(QLabel("ARINC 429 profili"), 0, 0)
        self.cb_tx_prof = QComboBox()
        self.cb_tx_prof.currentTextChanged.connect(lambda t: self._on_profile("tx_profile", t))
        gl.addWidget(self.cb_tx_prof, 0, 1)
        gl.addWidget(look.button("Düzenle…", None, app.open_arinc_dialog), 0, 2)
        llay.addWidget(g_tx)
        llay.addStretch(1)

        splitter.addWidget(left)

        # ---- Sağ panel (RX / TX sekmeleri)
        self.side_tabs = QTabWidget()
        self.side_tabs.setDocumentMode(True)
        splitter.addWidget(self.side_tabs)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        # RX alt sekmesi
        rx_page = QWidget()
        rlay = QVBoxLayout(rx_page)
        rlay.setContentsMargins(4, 4, 4, 4)
        rlay.setSpacing(6)
        self.lbl_rx_chk = look.label("", "cardTitle")
        rlay.addWidget(self.lbl_rx_chk)

        det = QTabWidget()
        det.setDocumentMode(True)
        self.tv_chk = _make_table(["Kontrol", "Sonuç"], [480, 90])
        det.addTab(self.tv_chk, "Kontroller")

        dur_w = QWidget()
        dlay = QVBoxLayout(dur_w)
        dlay.setContentsMargins(0, 4, 0, 0)
        self.tv_dur = _make_table(["Parametre", "µs", "clk"], [340, 100, 100])
        self.tv_dur.doubleClicked.connect(lambda idx: self._open_formula(self.tv_dur, idx.row(), ("µs", "clk")))
        dlay.addWidget(self.tv_dur, 1)
        dlay.addWidget(look.label("Formülü görmek için satıra çift tıklayın.", "muted"))
        det.addTab(dur_w, "Test toleransı eklenmiş süreler")

        mid_w = QWidget()
        mlay = QVBoxLayout(mid_w)
        mlay.setContentsMargins(0, 4, 0, 0)
        mlay.addWidget(look.label("Fiziksel en kötü durum, test toleransı eklenmemiş. Formülü görmek için satıra çift tıklayın.", "muted"))
        self.tv_mid = _make_table(["Parametre", "MIN", "NOM", "MAX"], [420, 90, 90, 90])
        self.tv_mid.doubleClicked.connect(lambda idx: self._open_formula(self.tv_mid, idx.row(), ("MIN", "NOM", "MAX")))
        mlay.addWidget(self.tv_mid, 1)
        det.addTab(mid_w, "Ara hesaplar ve formüller")
        rlay.addWidget(det, 1)

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
        tlay.setContentsMargins(4, 4, 4, 4)
        tlay.setSpacing(6)
        self.lbl_tx_chk = look.label("", "cardTitle")
        tlay.addWidget(self.lbl_tx_chk)
        self.lbl_tx_info = look.label("", "muted", wrap=True)
        tlay.addWidget(self.lbl_tx_info)

        g_tchk = QGroupBox("TX Kontrolleri")
        gtcl = QVBoxLayout(g_tchk)
        self.tv_tx_chk = _make_table(["Kontrol", "Sonuç"], [480, 90])
        gtcl.addWidget(self.tv_tx_chk, 1)
        tlay.addWidget(g_tchk, 1)

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

    def update_results(self, res, tx_res):
        ci = self.app.ci
        gf = f"%{ci.gf_ratio * 100:g} × {ci.gf_ref}" if ci.gf_mode == "ratio" else f"{ci.gf_clock} clock"
        self.lbl_glitch.setText(
            f"Filter: {gf} · Limit Pulse/Null/Gap "
            f"%{ci.pulse_glitch_pct * 100:g}/{ci.null_glitch_pct * 100:g}/{ci.gap_glitch_pct * 100:g}"
        )

        # RX tabloları
        if res is not None:
            _fill_table(
                self.tv_rx_regs,
                [[r[0], r[1], r[2], "" if r[3] is None else f"{r[3]:,}", r[4]] for r in res.regs],
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
                [[r[0], r[1], r[2], "" if r[3] is None else f"{r[3]:,}", r[4]] for r in tx_res["regs"]],
                ["fail" if r[5] else "" for r in tx_res["regs"]],
                [r[5] for r in tx_res["regs"]],
            )
            _fill_table(
                self.tv_tx_chk,
                [[n, "OK" if ok else "UYARI"] for n, ok in tx_res["checks"]],
                ["ok" if ok else "fail" for _, ok in tx_res["checks"]],
            )
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
