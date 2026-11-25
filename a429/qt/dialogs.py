"""Config ayar pencereleri, Formül penceresi ve Okuma ayarları diyaloğu (Qt)."""
from __future__ import annotations

import dataclasses

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QGridLayout, QGroupBox,
    QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox, QPushButton, QRadioButton,
    QVBoxLayout, QWidget,
)

from ..formulas import draw_formula
from ..ip import ReadSettings
from ..model import HB_50, HB_ARINC
from . import look

APP = "ARINC 429 Test Aracı"
GF_RATIO, GF_CLOCK = "Süreye oranlı", "Clock sayısı"
READ_MODES = {"Tümü": "all", "Son N kayıt": "last", "Okunmasın": "none"}
READ_MODES_REV = {v: k for k, v in READ_MODES.items()}

FPGA_NOTES = [
    "JEDEC JESD8C / Xilinx 7-serisi, UltraScale",
    "JEDEC / Xilinx: giriş eşikleri LVCMOS33 ile aynı",
    "Kullandığınız FPGA'nın datasheet'i (ör. bazı Intel/Lattice FPGA'larda VIH 1.7 V)",
]

ARINC_COLS = [
    ("Bit Rate (kbps)", [("rate_min", "MIN"), ("rate_nom", "NOM"), ("rate_max", "MAX")]),
    ("1 Bit Time", [(None, "µs"), ("bit_tol", "±%")]),
    ("½ Bit Time", [(None, "µs"), ("half_tol", "±%")]),
    ("Rise Time (µs)", [("rise_nom", "NOM"), ("rise_tol", "±")]),
    ("Fall Time (µs)", [("fall_nom", "NOM"), ("fall_tol", "±")]),
    ("Receiver genliği (V)", [("amp_min", "MIN"), ("amp_max", "MAX")]),
    ("k", [("k", "%10–%90")]),
]
ARINC_PERCENT = ("bit_tol", "half_tol")


def _set_bad(edit: QLineEdit, bad: bool):
    edit.setProperty("bad", "true" if bad else "false")
    look.repolish(edit)


def _to_float(text: str, name: str) -> float:
    try:
        return float(str(text).strip().replace(",", "."))
    except ValueError:
        raise ValueError(f"'{name}' alanı sayı olmalı (girilen: {text!r}).") from None


class ArincProfilesDialog(QDialog):
    """ARINC 429 profilleri düzenleme penceresi (RX ve TX ortak)."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setWindowTitle("ARINC 429 profilleri (RX ve TX ortak)")
        self._bad: set[QLineEdit] = set()
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(12, 12, 12, 12)
        self._lay.setSpacing(8)

        self._grid_host = QWidget()
        self._lay.addWidget(self._grid_host)

        bar = QHBoxLayout()
        bar.addWidget(QLabel("½ Bit Time ölçüm referansı:"))
        self.half_cb = QComboBox()
        self.half_cb.addItems([HB_ARINC, HB_50])
        self.half_cb.currentTextChanged.connect(self._half_changed)
        bar.addWidget(self.half_cb)
        bar.addStretch(1)
        self._lay.addLayout(bar)

        note = look.label(
            "RX ve TX aynı profil listesini kullanır; RX ve TX sütunlarından her biri ayrı profile ayarlanabilir. "
            "Kaynak: ARINC 429 Tutorial (OVIEW429, s. 11-12). k, Rise/Fall ölçümünün %10–%90 aralığıdır. "
            "1 Bit Time ve ½ Bit Time µs değerleri Bit Rate NOM'dan hesaplanır.",
            "muted",
            wrap=True,
        )
        self._lay.addWidget(note)

        foot = QHBoxLayout()
        foot.addWidget(look.label("Değişiklikler sonuçlara anında yansır.", "muted"))
        foot.addStretch(1)
        foot.addWidget(look.button("Kapat", "primary", self.close))
        self._lay.addLayout(foot)

        self.rebuild()

    def rebuild(self):
        self._bad.clear()
        old = self._grid_host.layout()
        if old is not None:
            while old.count():
                item = old.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
            QWidget().setLayout(old)

        grid = QGridLayout(self._grid_host)
        grid.setSpacing(4)
        grid.setContentsMargins(0, 0, 0, 0)

        for c, text in enumerate(("RX", "TX", "Profil")):
            lbl = look.label(text, "cardTitle")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(lbl, 0, c, 2, 1)

        c = 3
        for group, cols in ARINC_COLS:
            gl = look.label(group, "cardTitle")
            gl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(gl, 0, c, 1, len(cols))
            for _, head in cols:
                hl = look.label(head, "muted")
                hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                grid.addWidget(hl, 1, c)
                c += 1
        ol = look.label("İşlem", "cardTitle")
        ol.setAlignment(Qt.AlignmentFlag.AlignCenter)
        grid.addWidget(ol, 0, c, 2, 1)

        rx_grp = QButtonGroup(self._grid_host)
        tx_grp = QButtonGroup(self._grid_host)

        for r, prof in enumerate(self.app.ci.profiles, 2):
            rb_rx = QRadioButton()
            rb_rx.setChecked(prof.name == self.app.ci.profile)
            rb_rx.toggled.connect(lambda checked, n=prof.name: checked and self.app.select_profile("profile", n))
            rx_grp.addButton(rb_rx)
            grid.addWidget(rb_rx, r, 0, Qt.AlignmentFlag.AlignCenter)

            rb_tx = QRadioButton()
            rb_tx.setChecked(prof.name == self.app.ci.tx_profile)
            rb_tx.toggled.connect(lambda checked, n=prof.name: checked and self.app.select_profile("tx_profile", n))
            tx_grp.addButton(rb_tx)
            grid.addWidget(rb_tx, r, 1, Qt.AlignmentFlag.AlignCenter)

            grid.addWidget(QLabel(prof.name), r, 2)

            calc_labels: list[QLabel] = []
            col = 3
            for _, cols in ARINC_COLS:
                for field_, _head in cols:
                    if field_ is None:
                        cl = look.label("", "muted")
                        cl.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        cl.setMinimumWidth(52)
                        grid.addWidget(cl, r, col)
                        calc_labels.append(cl)
                    else:
                        val = getattr(prof, field_) * (100 if field_ in ARINC_PERCENT else 1)
                        ed = QLineEdit(f"{val:g}")
                        ed.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        ed.setFixedWidth(58)
                        ed.textChanged.connect(
                            lambda txt, p=prof, f=field_, w=ed, ls=calc_labels: self._edit(p, f, txt, w, ls)
                        )
                        grid.addWidget(ed, r, col)
                    col += 1
            self._update_calc(prof, calc_labels)

            ops = QWidget()
            olay = QHBoxLayout(ops)
            olay.setContentsMargins(0, 0, 0, 0)
            olay.setSpacing(3)
            olay.addWidget(look.button("Kopyala", None, lambda _, p=prof: self._new_copy(p)))
            olay.addWidget(look.button("Adlandır", None, lambda _, p=prof: self._rename(p)))
            olay.addWidget(look.button("Sil", None, lambda _, p=prof: self._delete(p)))
            grid.addWidget(ops, r, col)

        self.half_cb.blockSignals(True)
        self.half_cb.setCurrentText(self.app.ci.half_ref)
        self.half_cb.blockSignals(False)

    @staticmethod
    def _update_calc(prof, labels: list[QLabel]):
        ok = prof.rate_nom > 0
        labels[0].setText(f"{1000 / prof.rate_nom:g}" if ok else "–")
        labels[1].setText(f"{500 / prof.rate_nom:g}" if ok else "–")

    def _edit(self, prof, field_: str, text: str, edit: QLineEdit, labels: list[QLabel]):
        try:
            v = float(text.strip().replace(",", "."))
        except ValueError:
            _set_bad(edit, True)
            self._bad.add(edit)
            self.app.set_status("ARINC profil tablosunda geçersiz değer.")
            return
        _set_bad(edit, False)
        self._bad.discard(edit)
        v = v / 100 if field_ in ARINC_PERCENT else v
        setattr(prof, field_, v)
        self._update_calc(prof, labels)
        self.app.schedule_recalc()

    def _half_changed(self, text: str):
        self.app.ci.half_ref = text
        self.app.schedule_recalc()

    def _new_copy(self, prof):
        name, ok = QInputDialog.getText(self, APP, "Yeni profil adı (seçilen profilin kopyası):", text=f"{prof.name} kopya")
        name = name.strip()
        if not ok or not name:
            return
        if any(p.name == name for p in self.app.ci.profiles):
            QMessageBox.warning(self, APP, f"'{name}' adında bir profil zaten var.")
            return
        self.app.ci.profiles.append(dataclasses.replace(prof, name=name))
        self.app.refresh_profiles()
        self.rebuild()

    def _rename(self, prof):
        name, ok = QInputDialog.getText(self, APP, "Yeni ad:", text=prof.name)
        name = name.strip()
        if not ok or not name or name == prof.name:
            return
        if any(p.name == name for p in self.app.ci.profiles):
            QMessageBox.warning(self, APP, f"'{name}' adında bir profil zaten var.")
            return
        old = prof.name
        prof.name = name
        for k in ("profile", "tx_profile"):
            if getattr(self.app.ci, k) == old:
                setattr(self.app.ci, k, name)
        self.app.refresh_profiles()
        self.rebuild()

    def _delete(self, prof):
        if len(self.app.ci.profiles) <= 1:
            QMessageBox.information(self, APP, "En az bir profil kalmalı.")
            return
        if not look.confirm(self, APP, f"'{prof.name}' profili silinsin mi?", "Sil"):
            return
        self.app.ci.profiles.remove(prof)
        for k in ("profile", "tx_profile"):
            if getattr(self.app.ci, k) == prof.name:
                setattr(self.app.ci, k, self.app.ci.profiles[0].name)
        self.app.refresh_profiles()
        self.rebuild()

    def closeEvent(self, ev):
        if self._bad:
            QMessageBox.warning(self, APP, "Tabloda geçersiz değer var (kırmızı hücreler).")
            ev.ignore()
            return
        super().closeEvent(ev)


class IcProfileDialog(QDialog):
    """RX Receiver entegresi parametreleri penceresi."""

    ROWS = [
        ("v_one", "One/Zero eşiği (V)"),
        ("v_null", "Null eşiği (V)"),
        ("tplh", "Propagation Delay tPLH (ns)"),
        ("tphl", "Propagation Delay tPHL (ns)"),
        ("trr", "Output Transition trr (ns)"),
        ("tfr", "Output Transition tfr (ns)"),
        ("vcc", "VCC = çıkış salınımı (V)"),
    ]

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setWindowTitle("RX Receiver entegresi")
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        bar = QHBoxLayout()
        self.cb = QComboBox()
        self.cb.setMinimumWidth(180)
        self.cb.currentTextChanged.connect(self._selected)
        bar.addWidget(self.cb)
        bar.addWidget(look.button("Yeni", None, self._new))
        bar.addWidget(look.button("Adlandır", None, self._rename))
        bar.addWidget(look.button("Sil", None, self._delete))
        bar.addStretch(1)
        lay.addLayout(bar)

        grid = QGridLayout()
        grid.setSpacing(4)
        for j, h in enumerate(("MIN", "NOM", "MAX"), 1):
            hl = look.label(h, "cardTitle")
            hl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(hl, 0, j)

        self.edits: dict[str, list[QLineEdit]] = {}
        for r, (key, text) in enumerate(self.ROWS, 1):
            grid.addWidget(QLabel(text), r, 0)
            row_ed = []
            for j in range(3):
                ed = QLineEdit()
                ed.setFixedWidth(84)
                ed.setAlignment(Qt.AlignmentFlag.AlignCenter)
                ed.textChanged.connect(self._changed)
                grid.addWidget(ed, r, j + 1)
                row_ed.append(ed)
            self.edits[key] = row_ed

        grid.addWidget(QLabel("Çıkış VOH MIN / VOL MAX (V)"), 8, 0)
        self.voh = QLineEdit()
        self.voh.setFixedWidth(84)
        self.voh.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.voh.textChanged.connect(self._changed)
        self.vol = QLineEdit()
        self.vol.setFixedWidth(84)
        self.vol.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vol.textChanged.connect(self._changed)
        grid.addWidget(self.voh, 8, 1)
        grid.addWidget(self.vol, 8, 3)
        lay.addLayout(grid)

        lay.addWidget(look.label("Datasheet'te MIN değeri yoksa 0 yazın (en kötü durum).", "muted"))
        foot = QHBoxLayout()
        foot.addWidget(look.label("Değişiklikler sonuçlara anında yansır.", "muted"))
        foot.addStretch(1)
        foot.addWidget(look.button("Kapat", "primary", self.close))
        lay.addLayout(foot)

        self.load()

    def load(self):
        self._loading = True
        self.cb.blockSignals(True)
        self.cb.clear()
        self.cb.addItems([p.name for p in self.app.ci.ic_profiles])
        self.cb.setCurrentText(self.app.ci.ic.name)
        self.cb.blockSignals(False)
        ic = self.app.ci.ic
        for key, eds in self.edits.items():
            for ed, val in zip(eds, getattr(ic, key)):
                ed.setText(f"{val:g}")
                _set_bad(ed, False)
        self.voh.setText(f"{ic.voh_min:g}")
        self.vol.setText(f"{ic.vol_max:g}")
        _set_bad(self.voh, False)
        _set_bad(self.vol, False)
        self._loading = False

    def _selected(self, name: str):
        if self._loading or not name:
            return
        self.app.select_profile("ic_profile", name)
        self.load()

    def _changed(self):
        if self._loading:
            return
        ic = self.app.ci.ic
        ok_all = True
        for key, eds in self.edits.items():
            vals = []
            for ed in eds:
                try:
                    vals.append(float(ed.text().strip().replace(",", ".")))
                    _set_bad(ed, False)
                except ValueError:
                    _set_bad(ed, True)
                    ok_all = False
            if len(vals) == 3:
                setattr(ic, key, tuple(vals))
        for attr, ed in (("voh_min", self.voh), ("vol_max", self.vol)):
            try:
                setattr(ic, attr, float(ed.text().strip().replace(",", ".")))
                _set_bad(ed, False)
            except ValueError:
                _set_bad(ed, True)
                ok_all = False
        if ok_all:
            self.app.schedule_recalc()

    def _new(self):
        cur = self.app.ci.ic
        name, ok = QInputDialog.getText(self, APP, "Yeni entegre profili adı:", text=f"{cur.name} kopya")
        name = name.strip()
        if not ok or not name:
            return
        if any(p.name == name for p in self.app.ci.ic_profiles):
            QMessageBox.warning(self, APP, f"'{name}' adında bir profil zaten var.")
            return
        self.app.ci.ic_profiles.append(dataclasses.replace(cur, name=name))
        self.app.ci.ic_profile = name
        self.app.refresh_profiles()
        self.load()

    def _rename(self):
        cur = self.app.ci.ic
        name, ok = QInputDialog.getText(self, APP, "Yeni ad:", text=cur.name)
        name = name.strip()
        if not ok or not name or name == cur.name:
            return
        if any(p.name == name for p in self.app.ci.ic_profiles):
            QMessageBox.warning(self, APP, f"'{name}' adında bir profil zaten var.")
            return
        cur.name = name
        self.app.ci.ic_profile = name
        self.app.refresh_profiles()
        self.load()

    def _delete(self):
        if len(self.app.ci.ic_profiles) <= 1:
            QMessageBox.information(self, APP, "En az bir profil kalmalı.")
            return
        cur = self.app.ci.ic
        if not look.confirm(self, APP, f"'{cur.name}' profili silinsin mi?", "Sil"):
            return
        self.app.ci.ic_profiles.remove(cur)
        self.app.ci.ic_profile = self.app.ci.ic_profiles[0].name
        self.app.refresh_profiles()
        self.load()


class FpgaStandardsDialog(QDialog):
    """RX FPGA giriş standartları penceresi."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setWindowTitle("RX FPGA giriş standartları")
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        grid = QGridLayout()
        for j, h in enumerate(("Standart", "VIL MAX (V)", "VIH MIN (V)", "Kaynak")):
            grid.addWidget(look.label(h, "cardTitle"), 0, j)

        self.rows: list[tuple[QLineEdit, QLineEdit, QLineEdit]] = []
        for i in range(3):
            e0 = QLineEdit()
            e0.setFixedWidth(120)
            e1 = QLineEdit()
            e1.setFixedWidth(80)
            e1.setAlignment(Qt.AlignmentFlag.AlignCenter)
            e2 = QLineEdit()
            e2.setFixedWidth(80)
            e2.setAlignment(Qt.AlignmentFlag.AlignCenter)
            for e in (e0, e1, e2):
                e.textChanged.connect(self._changed)
            grid.addWidget(e0, i + 1, 0)
            grid.addWidget(e1, i + 1, 1)
            grid.addWidget(e2, i + 1, 2)
            grid.addWidget(look.label(FPGA_NOTES[i], "muted"), i + 1, 3)
            self.rows.append((e0, e1, e2))
        lay.addLayout(grid)

        lay.addWidget(look.label("Giriş eşiğinin VIL MAX ile VIH MIN arasında olduğu, Schmitt Trigger bulunmadığı varsayılır.", "muted"))
        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(look.button("Kapat", "primary", self.close))
        lay.addLayout(foot)
        self.load()

    def load(self):
        self._loading = True
        for (e0, e1, e2), r in zip(self.rows, self.app.ci.fpga_table):
            e0.setText(str(r[0]))
            e1.setText(f"{float(r[1]):g}")
            e2.setText(f"{float(r[2]):g}")
            _set_bad(e1, False)
            _set_bad(e2, False)
        self._loading = False

    def _changed(self):
        if self._loading:
            return
        old_names = [r[0] for r in self.app.ci.fpga_table]
        new_table = []
        ok_all = True
        for i, (e0, e1, e2) in enumerate(self.rows):
            name = e0.text().strip() or old_names[i]
            try:
                vil = float(e1.text().strip().replace(",", "."))
                _set_bad(e1, False)
            except ValueError:
                _set_bad(e1, True)
                ok_all = False
                vil = float(self.app.ci.fpga_table[i][1])
            try:
                vih = float(e2.text().strip().replace(",", "."))
                _set_bad(e2, False)
            except ValueError:
                _set_bad(e2, True)
                ok_all = False
                vih = float(self.app.ci.fpga_table[i][2])
            new_table.append([name, vil, vih])
        if ok_all:
            sel = self.app.ci.fpga_std
            new_names = [r[0] for r in new_table]
            if sel in old_names and sel not in new_names:
                sel = new_names[old_names.index(sel)]
            self.app.ci.fpga_table = new_table
            self.app.ci.fpga_std = sel if sel in new_names else new_names[0]
            self.app.refresh_fpga_combo()
            self.app.schedule_recalc()


class GlitchDialog(QDialog):
    """RX Glitch Filter ve Glitch Error limitleri penceresi."""

    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.setWindowTitle("RX Glitch Filter ve limitler")
        self._loading = False
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)

        g1 = QGroupBox("Glitch Filter")
        gl1 = QGridLayout(g1)
        gl1.addWidget(QLabel("Hesap yöntemi"), 0, 0)
        self.mode_cb = QComboBox()
        self.mode_cb.addItems([GF_RATIO, GF_CLOCK])
        self.mode_cb.currentTextChanged.connect(self._changed)
        gl1.addWidget(self.mode_cb, 0, 1)

        self.lbl_ratio = QLabel("Oran (%)")
        self.ed_ratio = QLineEdit()
        self.ed_ratio.textChanged.connect(self._changed)
        gl1.addWidget(self.lbl_ratio, 1, 0)
        gl1.addWidget(self.ed_ratio, 1, 1)

        self.lbl_ref = QLabel("Oranın referans süresi")
        self.cb_ref = QComboBox()
        self.cb_ref.addItems(["Min Pulse", "Min Null", "Min Bit"])
        self.cb_ref.currentTextChanged.connect(self._changed)
        gl1.addWidget(self.lbl_ref, 2, 0)
        gl1.addWidget(self.cb_ref, 2, 1)

        self.lbl_clk = QLabel("Clock sayısı")
        self.ed_clk = QLineEdit()
        self.ed_clk.textChanged.connect(self._changed)
        gl1.addWidget(self.lbl_clk, 3, 0)
        gl1.addWidget(self.ed_clk, 3, 1)
        lay.addWidget(g1)

        g2 = QGroupBox("Glitch Error limitleri")
        gl2 = QGridLayout(g2)
        self.ed_pulse = QLineEdit()
        self.ed_null = QLineEdit()
        self.ed_gap = QLineEdit()
        for r, (txt, ed) in enumerate((
            ("Pulse içinde MAX Glitch (%)", self.ed_pulse),
            ("Null içinde MAX Glitch (%)", self.ed_null),
            ("Word Gap içinde MAX Glitch (%)", self.ed_gap),
        )):
            gl2.addWidget(QLabel(txt), r, 0)
            ed.textChanged.connect(self._changed)
            gl2.addWidget(ed, r, 1)
        gl2.addWidget(QLabel("Pulse/Null referans süresi"), 3, 0)
        self.cb_base = QComboBox()
        self.cb_base.addItems(["MIN", "NOM", "MAX"])
        self.cb_base.currentTextChanged.connect(self._changed)
        gl2.addWidget(self.cb_base, 3, 1)
        gl2.addWidget(look.label("Word Gap referans süresi sabittir: 4 × Min Bit", "muted"), 4, 0, 1, 2)
        lay.addWidget(g2)

        foot = QHBoxLayout()
        foot.addWidget(look.label("Değişiklikler sonuçlara anında yansır.", "muted"))
        foot.addStretch(1)
        foot.addWidget(look.button("Kapat", "primary", self.close))
        lay.addLayout(foot)

        self.load()

    def load(self):
        self._loading = True
        ci = self.app.ci
        self.mode_cb.setCurrentText(GF_CLOCK if ci.gf_mode == "clock" else GF_RATIO)
        self.ed_ratio.setText(f"{ci.gf_ratio * 100:g}")
        self.cb_ref.setCurrentText(ci.gf_ref)
        self.ed_clk.setText(str(ci.gf_clock))
        self.ed_pulse.setText(f"{ci.pulse_glitch_pct * 100:g}")
        self.ed_null.setText(f"{ci.null_glitch_pct * 100:g}")
        self.ed_gap.setText(f"{ci.gap_glitch_pct * 100:g}")
        self.cb_base.setCurrentText(ci.glitch_base)
        self._loading = False
        self._sync_vis()

    def _sync_vis(self):
        by_clk = self.mode_cb.currentText() == GF_CLOCK
        for w in (self.lbl_ratio, self.ed_ratio, self.lbl_ref, self.cb_ref):
            w.setVisible(not by_clk)
        for w in (self.lbl_clk, self.ed_clk):
            w.setVisible(by_clk)

    def _changed(self):
        if self._loading:
            return
        self._sync_vis()
        ci = self.app.ci
        ci.gf_mode = "clock" if self.mode_cb.currentText() == GF_CLOCK else "ratio"
        ci.gf_ref = self.cb_ref.currentText()
        ci.glitch_base = self.cb_base.currentText()
        ok_all = True

        def parse(ed: QLineEdit, scale: float = 1.0, as_int: bool = False):
            nonlocal ok_all
            try:
                v = float(ed.text().strip().replace(",", ".")) / scale
                _set_bad(ed, False)
                return int(v) if as_int else v
            except ValueError:
                _set_bad(ed, True)
                ok_all = False
                return None

        if ci.gf_mode == "clock":
            v = parse(self.ed_clk, 1.0, True)
            if v is not None:
                ci.gf_clock = v
        else:
            v = parse(self.ed_ratio, 100.0)
            if v is not None:
                ci.gf_ratio = v
        for attr, ed in (("pulse_glitch_pct", self.ed_pulse), ("null_glitch_pct", self.ed_null), ("gap_glitch_pct", self.ed_gap)):
            v = parse(ed, 100.0)
            if v is not None:
                setattr(ci, attr, v)
        if ok_all:
            self.app.schedule_recalc()


class FormulaDialog(QDialog):
    """Tek bir RX ara hesap satırının formülünü gösterir."""

    def __init__(self, parent, key: str, shown: str):
        super().__init__(parent)
        self.setWindowTitle(f"RX Formül – {key}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 10, 10, 10)
        lbl = look.label(f"Güncel değer:  {shown}", "cardTitle")
        lay.addWidget(lbl)
        fig = Figure(dpi=100)
        w, h = draw_formula(fig, key)
        canvas = FigureCanvasQTAgg(fig)
        canvas.setMinimumSize(int(w * 100), int(h * 100))
        lay.addWidget(canvas, 1)
        canvas.draw()


class ReadSettingsDialog(QDialog):
    """Okunacak RX verileri ve çıktı dosyaları ayarları."""

    def __init__(self, parent, rs: ReadSettings):
        super().__init__(parent)
        self.setWindowTitle("Okuma ayarları")
        self._rs = rs
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(10)

        g1 = QGroupBox("Okunacak RX verileri")
        gl1 = QGridLayout(g1)
        self.opts: dict[str, tuple[QComboBox, QLineEdit]] = {}
        for r, (key, title) in enumerate((("word", "Word"), ("error", "Error"), ("bit", "Bit Diagnostic"))):
            gl1.addWidget(QLabel(title), r, 0)
            cb = QComboBox()
            cb.addItems(list(READ_MODES))
            cb.setCurrentText(READ_MODES_REV.get(getattr(rs, f"read_{key}"), "Tümü"))
            ed = QLineEdit(str(getattr(rs, f"read_{key}_n")))
            ed.setFixedWidth(70)
            cb.currentTextChanged.connect(lambda txt, e=ed: e.setVisible(txt == "Son N kayıt"))
            ed.setVisible(cb.currentText() == "Son N kayıt")
            gl1.addWidget(cb, r, 1)
            gl1.addWidget(ed, r, 2)
            self.opts[key] = (cb, ed)
        gl1.addWidget(look.label("Bit Diagnostic için N, Word sayısıdır (her Word 32 Bit). En yeni kayıtlar okunur.", "muted", True), 3, 0, 1, 3)
        gl1.addWidget(look.label("Okuma süresince kanal FREEZE=1 tutulur ve Debug Bridge kilitlenir.", "muted", True), 4, 0, 1, 3)
        lay.addWidget(g1)

        g2 = QGroupBox("Okuma ve yazma dosyaları")
        gl2 = QGridLayout(g2)
        gl2.addWidget(QLabel("Klasör"), 0, 0)
        self.ed_dir = QLineEdit(rs.out_dir)
        self.ed_dir.setMinimumWidth(280)
        gl2.addWidget(self.ed_dir, 0, 1)
        gl2.addWidget(look.button("…", None, self._pick_dir), 0, 2)
        self.chk_txt = QCheckBox("TTL/Excel txt dosyalarını da yaz")
        self.chk_txt.setChecked(rs.auto_txt)
        gl2.addWidget(self.chk_txt, 1, 0, 1, 3)
        self.chk_wlog = QCheckBox("Register yazma logunu da kaydet")
        self.chk_wlog.setChecked(rs.auto_write_log)
        gl2.addWidget(self.chk_wlog, 2, 0, 1, 3)
        self.chk_verb = QCheckBox("Okumada tüm erişimleri Debug Bridge trafik günlüğüne yaz")
        self.chk_verb.setChecked(rs.verbose_bridge_log)
        gl2.addWidget(self.chk_verb, 3, 0, 1, 3)
        lay.addWidget(g2)

        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(look.button("İptal", None, self.reject))
        foot.addWidget(look.button("Tamam", "primary", self._apply))
        lay.addLayout(foot)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "Okuma klasörü", self.ed_dir.text())
        if d:
            self.ed_dir.setText(d)

    def _apply(self):
        rs = self._rs
        for key, (cb, ed) in self.opts.items():
            mode = READ_MODES[cb.currentText()]
            if mode == "last":
                try:
                    n = int(_to_float(ed.text(), f"{key} kayıt sayısı"))
                    if n < 1:
                        raise ValueError("Kayıt sayısı en az 1 olmalı.")
                except ValueError as e:
                    QMessageBox.warning(self, APP, str(e))
                    return
                setattr(rs, f"read_{key}_n", n)
            setattr(rs, f"read_{key}", mode)
        rs.out_dir = self.ed_dir.text().strip() or rs.out_dir
        rs.auto_txt = self.chk_txt.isChecked()
        rs.auto_write_log = self.chk_wlog.isChecked()
        rs.verbose_bridge_log = self.chk_verb.isChecked()
        self.accept()
