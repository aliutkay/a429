"""Test sekmesi: TX -> RX loopback ile ARINC 429 IP ve hat entegrelerinin otomatik testi (a429/selftest.py)."""
from __future__ import annotations

import os
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QListWidget,
    QListWidgetItem, QProgressBar, QSpinBox, QSplitter, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import selftest
from ..regs import channel_label
from . import look

STATUS_STYLE = {"PASS": ("GEÇTİ", "success"), "FAIL": ("KALDI", "danger"), "ERROR": ("HATA", "danger"),
                "SKIP": ("ATLANDI", "muted")}


class TestTab(QWidget):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.report: dict | None = None
        self._rx_boxes: dict[str, QCheckBox] = {}

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split)

        # ---------------------------------------------------------------- Sol: kurulum
        left = look.Card(margins=12, spacing=8, object_name="SubCard")
        left.lay.addWidget(look.label("Loopback Test Kurulumu", "cardTitle"))
        left.lay.addWidget(look.label(
            "Kartın ARINC TX çıkışını (line driver) aşağıda işaretlediğiniz RX girişlerine (line receiver) dışarıdan "
            "bağlayın. TX BIT kanalı TX hattını kart üzerindeki kendi alıcısıyla dinler. Test TX'ten gönderir, TX BIT'i "
            "ve RX'leri karşılaştırır; IP'yi ve sürücü/alıcı entegrelerini birlikte doğrular.", "muted", True))

        left.lay.addWidget(look.label("TX'e bağlı RX kanalları", "muted"))
        self.rx_box = QWidget()
        self.rx_grid = QGridLayout(self.rx_box)
        self.rx_grid.setContentsMargins(0, 0, 0, 0)
        self.rx_grid.setHorizontalSpacing(12)
        left.lay.addWidget(self.rx_box)
        self.chk_tb = QCheckBox("TX BIT (TB) kanalını ve Word Checker'ı dahil et")
        self.chk_tb.setChecked(True)
        left.lay.addWidget(self.chk_tb)

        sp = QHBoxLayout()
        sp.addWidget(look.label("Hızlar:", "muted"))
        self.chk_hs = QCheckBox("High Speed (100 kbps)")
        self.chk_ls = QCheckBox("Low Speed (12.5 kbps)")
        self.chk_hs.setChecked(True)
        self.chk_ls.setChecked(True)
        sp.addWidget(self.chk_hs)
        sp.addWidget(self.chk_ls)
        sp.addStretch(1)
        left.lay.addLayout(sp)

        g = QGridLayout()
        g.setHorizontalSpacing(8)
        g.addWidget(look.label("Desen uzunluğu (Word)", "muted"), 0, 0)
        self.sp_pattern = QSpinBox()
        self.sp_pattern.setRange(8, 500)
        self.sp_pattern.setValue(35)
        self.sp_pattern.setToolTip("Veri bütünlüğü deseni: 0x00.., 0x7F.., 0x55.., 0x2A.., walking-1 (LS'de 1/3'ü)")
        g.addWidget(self.sp_pattern, 0, 1)
        g.addWidget(look.label("Art arda Word sayısı", "muted"), 1, 0)
        self.sp_burst = QSpinBox()
        self.sp_burst.setRange(8, 5000)
        self.sp_burst.setValue(40)
        self.sp_burst.setToolTip("Minimum gap (4 bit) ile art arda gönderilecek Word sayısı (LS'de 1/4'ü)")
        g.addWidget(self.sp_burst, 1, 1)
        left.lay.addLayout(g)
        self.chk_stop_fail = QCheckBox("İlk başarısız testte dur")
        left.lay.addWidget(self.chk_stop_fail)

        th = QHBoxLayout()
        th.addWidget(look.label("Testler", "muted"))
        th.addStretch(1)
        th.addWidget(look.button("Tümü", None, lambda: self._check_all(True)))
        th.addWidget(look.button("Hiçbiri", None, lambda: self._check_all(False)))
        left.lay.addLayout(th)
        self.lst = QListWidget()
        self.lst.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for tid, title, _fn, per_speed in selftest.CATALOG:
            it = QListWidgetItem(title + ("  (HS / LS)" if per_speed else ""))
            it.setData(Qt.ItemDataRole.UserRole, tid)
            flags = it.flags() | Qt.ItemFlag.ItemIsUserCheckable
            if tid in selftest.ALWAYS:
                flags &= ~Qt.ItemFlag.ItemIsEnabled
            it.setFlags(flags)
            it.setCheckState(Qt.CheckState.Checked)
            self.lst.addItem(it)
        left.lay.addWidget(self.lst, 1)
        left.setMinimumWidth(340)
        split.addWidget(left)

        # ---------------------------------------------------------------- Sağ: sonuçlar
        right = look.Card(margins=12, spacing=8, object_name="SubCard")
        hdr = QHBoxLayout()
        hdr.addWidget(look.label("Test Sonuçları", "cardTitle"))
        self.pill = look.Pill("Koşulmadı", "")
        hdr.addWidget(self.pill)
        self.lbl_time = look.label("", "muted")
        hdr.addWidget(self.lbl_time)
        hdr.addStretch(1)
        self.btn_run = look.button("▶ Testi Başlat", "primary", self._run)
        self.btn_stop = look.button("Durdur", None, app.do_stop)
        self.btn_save = look.button("Raporu Kaydet…", None, self._save)
        self.btn_save.setEnabled(False)
        for b in (self.btn_run, self.btn_stop, self.btn_save):
            hdr.addWidget(b)
        right.lay.addLayout(hdr)
        self.prog = QProgressBar()
        self.prog.setRange(0, 100)
        self.prog.setValue(0)
        right.lay.addWidget(self.prog)

        self.tree = QTreeWidget()
        self.tree.setColumnCount(4)
        self.tree.setHeaderLabels(["Sonuç", "Test / Kontrol", "Süre", "Ayrıntı"])
        self.tree.setRootIsDecorated(True)
        self.tree.setAlternatingRowColors(True)
        h = self.tree.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setStretchLastSection(True)
        self.tree.setColumnWidth(1, 430)
        right.lay.addWidget(self.tree, 1)

        self.lbl_note = look.label(
            "Test TX ve RX config'ini değiştirir (HS / LS / Custom), hat override ve scheduler kullanır; sonunda High "
            "Speed preset, Word Transmitter ve açık logger'larla bırakır. Bağlı olmayan RX'leri işaretlemeyin.",
            "muted", True)
        right.lay.addWidget(self.lbl_note)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([380, 1000])

    # ---------------------------------------------------------------- kurulum
    def populate_channels(self, rm):
        for cb in self._rx_boxes.values():
            cb.setParent(None)
        self._rx_boxes.clear()
        rx = [c for c in rm.channels() if c.startswith("RX")] if rm.is_loaded() else []
        for i, ch in enumerate(rx):
            cb = QCheckBox(f"{ch}  ←  TX")
            cb.setChecked(ch == "RX0")
            self.rx_grid.addWidget(cb, i // 4, i % 4)
            self._rx_boxes[ch] = cb
        self.chk_tb.setEnabled(rm.is_loaded() and rm.has("TB_CTRL"))
        self.chk_tb.setChecked(rm.is_loaded() and rm.has("TB_CTRL"))

    def _check_all(self, on: bool):
        for i in range(self.lst.count()):
            it = self.lst.item(i)
            if it.flags() & Qt.ItemFlag.ItemIsEnabled:
                it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def options(self) -> dict:
        sel = [self.lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lst.count())
               if self.lst.item(i).checkState() == Qt.CheckState.Checked]
        speeds = tuple(s for s, cb in (("HS", self.chk_hs), ("LS", self.chk_ls)) if cb.isChecked())
        return {"rx": [c for c, cb in self._rx_boxes.items() if cb.isChecked()], "tb": self.chk_tb.isChecked(),
                "selected": sel, "speeds": speeds or ("HS",), "pattern_len": self.sp_pattern.value(),
                "burst_words": self.sp_burst.value(), "stop_on_fail": self.chk_stop_fail.isChecked()}

    def set_controls(self, can_run: bool, busy: bool, tip: str = ""):
        self.btn_run.setEnabled(can_run and not busy)
        self.btn_run.setToolTip(tip or "Seçili testleri TX → RX loopback üzerinden koşar")
        self.btn_stop.setEnabled(busy)

    # ---------------------------------------------------------------- koşum
    def _run(self):
        o = self.options()
        if not o["rx"] and not o["tb"]:
            look.confirm(self, "Loopback Testi", "En az bir RX kanalı ya da TX BIT seçin.", "Tamam", "Kapat")
            return
        self.tree.clear()
        self.report = None
        self.btn_save.setEnabled(False)
        self.pill.set("Koşuyor…", "accent")
        self.lbl_time.setText("")
        self.prog.setValue(0)
        self.app.do_run_selftest(o)

    def on_progress(self, done: int, total: int, msg: str):
        self.prog.setMaximum(max(1, total))
        self.prog.setValue(min(done, max(1, total)))
        self.prog.setFormat(f"%p%  ·  {msg}")

    def add_result(self, r: selftest.TestResult):
        text, role = STATUS_STYLE.get(r.status, (r.status, ""))
        top = QTreeWidgetItem([text, r.title + (f"  ·  {r.speed}" if r.speed else ""), f"{r.duration_s:.2f} s",
                               r.summary])
        col = look.color(role) if role in ("success", "danger") else look.color("muted")
        top.setForeground(0, QBrush(col))
        f = top.font(0)
        f.setBold(True)
        top.setFont(0, f)
        for ck in r.checks:
            mark = {True: "✓", False: "✗", None: "·"}[ck.ok]
            it = QTreeWidgetItem([mark, ck.name, "", ck.detail])
            it.setToolTip(1, ck.name)
            it.setToolTip(3, ck.detail)
            if ck.ok is False:
                it.setForeground(0, QBrush(look.color("danger")))
                it.setForeground(1, QBrush(look.color("danger")))
            elif ck.ok:
                it.setForeground(0, QBrush(look.color("success")))
            top.addChild(it)
        for n in r.notes:
            top.addChild(QTreeWidgetItem(["!", n, "", ""]))
        if r.measurements:
            import json
            m = QTreeWidgetItem(["", "Ölçümler", "", json.dumps(r.measurements, ensure_ascii=False)])
            m.setToolTip(3, json.dumps(r.measurements, ensure_ascii=False, indent=1))
            top.addChild(m)
        self.tree.addTopLevelItem(top)
        top.setExpanded(r.status != "PASS")
        self.tree.scrollToItem(top)

    def set_report(self, rep: dict | None, error: str = ""):
        if rep is None:
            self.pill.set("Hata" if error else "Durduruldu", "err" if error else "warn")
            self.lbl_time.setText(error)
            return
        self.report = rep
        c = rep["counts"]
        if rep["aborted"]:
            self.pill.set("Durduruldu", "warn")
        elif rep["passed"]:
            self.pill.set(f"GEÇTİ ✓  ({c['PASS']} test)", "ok")
        else:
            self.pill.set(f"KALDI ✗  ({c['FAIL'] + c['ERROR']} başarısız / {len(rep['results'])})", "err")
        sim = rep.get("sim", {}).get("cycles")
        self.lbl_time.setText(f"{rep['duration_s']} s" + (f" · RTL {sim / 5e4:.1f} ms simüle" if sim else ""))
        self.btn_save.setEnabled(True)
        self.prog.setFormat("%p%")

    def _save(self):
        if not self.report:
            return
        d = self.app.rs.out_dir or os.path.expanduser("~")
        name = os.path.join(d, time.strftime("a429_loopback_test_%Y%m%d_%H%M%S.txt"))
        p, flt = QFileDialog.getSaveFileName(self, "Test raporunu kaydet", name, "Metin (*.txt);;JSON (*.json)")
        if not p:
            return
        text = selftest.report_json(self.report) if p.endswith(".json") or "JSON" in flt else selftest.report_text(self.report)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.app.log(f"[Test] Rapor kaydedildi: {p}")


def _label(ch: str) -> str:
    return channel_label(ch)
