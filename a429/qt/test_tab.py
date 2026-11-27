"""Test sekmesi: Loopback (a429/selftest.py) ve Ballard Dış Doğrulama (a429/busbox_test.py) otomatik testleri."""
from __future__ import annotations

import json
import os
import time

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView,
    QListWidget, QListWidgetItem, QProgressBar, QSpinBox, QSplitter, QStackedWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import busbox_test, selftest
from ..ballard import CardInfo
from ..regs import channel_label
from . import look

STATUS_STYLE = {"PASS": ("GEÇTİ", "success"), "FAIL": ("KALDI", "danger"), "ERROR": ("HATA", "danger"),
                "SKIP": ("ATLANDI", "muted")}

NOTE_LOOPBACK = (
    "Loopback modu: TX ve RX config'ini değiştirir (HS / LS / Custom), hat override ve scheduler kullanır; "
    "sonunda High Speed preset, Word Transmitter ve açık logger'larla bırakır. Bağlı olmayan RX'leri işaretlemeyin."
)
NOTE_BALLARD = (
    "Dış Doğrulama modu (Ballard BTIDriver 64-bit): Kart TX ↔ Ballard RX ve Ballard TX ↔ Kart RX ayrı ayrı "
    "doğrulanır; FPGA saat sapması, bit sırası ve alıcı entegre zamanlaması bağımsız ölçülür."
)


class TestTab(QWidget):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.report: dict | None = None
        self._rx_boxes: dict[str, QCheckBox] = {}
        self._bb_rx_boxes: dict[str, QCheckBox] = {}
        self._bb_cards: list[CardInfo] = []
        self._bb_dll_dir: str | None = None
        self._can_run_base = False
        self._busy = False
        self._bb_scanning = False
        self._tip_base = ""

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split)

        # ---------------------------------------------------------------- Sol: kurulum
        left = look.Card(margins=12, spacing=8, object_name="SubCard")
        left.lay.addWidget(look.label("Otomatik Test Kurulumu", "cardTitle"))

        mrow = QHBoxLayout()
        mrow.addWidget(look.label("Test Modu:", "muted"))
        self.cb_mode = QComboBox()
        self.cb_mode.addItem("Loopback Testi (TX → RX)", "loopback")
        self.cb_mode.addItem("Dış Doğrulama Modu (Ballard BusBox / OmniBusBox)", "ballard")
        self.cb_mode.currentIndexChanged.connect(self._on_mode_changed)
        mrow.addWidget(self.cb_mode, 1)
        left.lay.addLayout(mrow)

        self.mode_stack = QStackedWidget()
        left.lay.addWidget(self.mode_stack)

        # ---- Sayfa 0: Loopback kurulumu
        pg_lb = QWidget()
        l_lb = QVBoxLayout(pg_lb)
        l_lb.setContentsMargins(0, 0, 0, 0)
        l_lb.setSpacing(6)
        l_lb.addWidget(look.label(
            "Kartın ARINC TX çıkışını (line driver) aşağıda işaretlediğiniz RX girişlerine (line receiver) dışarıdan "
            "bağlayın. TX BIT kanalı TX hattını kart üzerindeki kendi alıcısıyla dinler. Test TX'ten gönderir, TX BIT'i "
            "ve RX'leri karşılaştırır; IP'yi ve sürücü/alıcı entegrelerini birlikte doğrular.", "muted", True))
        l_lb.addWidget(look.label("TX'e bağlı RX kanalları", "muted"))
        self.rx_box = QWidget()
        self.rx_grid = QGridLayout(self.rx_box)
        self.rx_grid.setContentsMargins(0, 0, 0, 0)
        self.rx_grid.setHorizontalSpacing(12)
        l_lb.addWidget(self.rx_box)
        self.chk_tb = QCheckBox("TX BIT (TB) kanalını ve Word Checker'ı dahil et")
        self.chk_tb.setChecked(True)
        l_lb.addWidget(self.chk_tb)
        self.mode_stack.addWidget(pg_lb)

        # ---- Sayfa 1: Ballard Dış Doğrulama kurulumu
        pg_bb = QWidget()
        l_bb = QVBoxLayout(pg_bb)
        l_bb.setContentsMargins(0, 0, 0, 0)
        l_bb.setSpacing(6)
        l_bb.addWidget(look.label(
            "Kart TX çıkışını Ballard RX kanalına, Ballard TX çıkışını seçili Kart RX girişlerine bağlayın. "
            "IP ve sürücü/alıcı entegreleri bağımsız referans cihazla ayrı ayrı test edilir.", "muted", True))

        brow = QHBoxLayout()
        self.cb_bb_card = QComboBox()
        self.cb_bb_card.addItem("Kart #0 · Core #0 (taranmadı)", (0, 0))
        self.cb_bb_card.currentIndexChanged.connect(self._on_bb_card_changed)
        brow.addWidget(self.cb_bb_card, 1)
        self.btn_bb_scan = look.button("Tara", None, self._scan_ballard, "Bağlı Ballard cihazlarını ve 429 kanallarını tara")
        self.btn_bb_dll = look.button("DLL…", None, self._pick_dll_dir, "BTICARD64.DLL / BTI42964.DLL klasörünü seç (isteğe bağlı)")
        brow.addWidget(self.btn_bb_scan)
        brow.addWidget(self.btn_bb_dll)
        l_bb.addLayout(brow)

        self.lbl_bb_status = look.label("Cihaz taramak için 'Tara' düğmesine basın (BTICARD64.DLL / BTI42964.DLL).", "muted", True)
        l_bb.addWidget(self.lbl_bb_status)

        bg = QGridLayout()
        bg.setHorizontalSpacing(8)
        bg.setVerticalSpacing(4)
        self.chk_bb_tx = QCheckBox("Kart TX → Ballard RX")
        self.chk_bb_tx.setChecked(True)
        self.chk_bb_tx.toggled.connect(self._sync_bb_enabled)
        self.cb_bb_rx_ch = QComboBox()
        for ch in range(16):
            self.cb_bb_rx_ch.addItem(f"RX CH{ch}", ch)
        bg.addWidget(self.chk_bb_tx, 0, 0)
        bg.addWidget(self.cb_bb_rx_ch, 0, 1)

        self.chk_bb_rx = QCheckBox("Ballard TX → Kart RX")
        self.chk_bb_rx.setChecked(True)
        self.chk_bb_rx.toggled.connect(self._sync_bb_enabled)
        self.cb_bb_tx_ch = QComboBox()
        for ch in range(16):
            self.cb_bb_tx_ch.addItem(f"TX CH{ch}", ch)
        self.cb_bb_tx_ch.setCurrentIndex(4)
        bg.addWidget(self.chk_bb_rx, 1, 0)
        bg.addWidget(self.cb_bb_tx_ch, 1, 1)
        l_bb.addLayout(bg)

        l_bb.addWidget(look.label("Ballard TX'e bağlı Kart RX kanalları", "muted"))
        self.bb_rx_box = QWidget()
        self.bb_rx_grid = QGridLayout(self.bb_rx_box)
        self.bb_rx_grid.setContentsMargins(0, 0, 0, 0)
        self.bb_rx_grid.setHorizontalSpacing(12)
        l_bb.addWidget(self.bb_rx_box)

        self.chk_bb_tb = QCheckBox("TX BIT (TB) yankısını ve Checker'ı dahil et")
        self.chk_bb_tb.setChecked(False)
        l_bb.addWidget(self.chk_bb_tb)
        self._sync_bb_enabled()
        self.mode_stack.addWidget(pg_bb)

        # ---- Ortak ayarlar
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

        self.list_stack = QStackedWidget()
        self.lst = self._build_test_list(selftest.CATALOG, selftest.ALWAYS)
        self.lst_bb = self._build_test_list(
            [(t[0], t[1], t[2], t[3]) for t in busbox_test.CATALOG],
            busbox_test.ALWAYS,
        )
        self.list_stack.addWidget(self.lst)
        self.list_stack.addWidget(self.lst_bb)
        left.lay.addWidget(self.list_stack, 1)
        left.setMinimumWidth(360)
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

        self.lbl_note = look.label(NOTE_LOOPBACK, "muted", True)
        right.lay.addWidget(self.lbl_note)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([400, 1000])

    @staticmethod
    def _build_test_list(catalog, always) -> QListWidget:
        lst = QListWidget()
        lst.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        for tid, title, _fn, per_speed in catalog:
            it = QListWidgetItem(title + ("  (HS / LS)" if per_speed else ""))
            it.setData(Qt.ItemDataRole.UserRole, tid)
            flags = it.flags() | Qt.ItemFlag.ItemIsUserCheckable
            if tid in always:
                flags &= ~Qt.ItemFlag.ItemIsEnabled
            it.setFlags(flags)
            it.setCheckState(Qt.CheckState.Checked)
            lst.addItem(it)
        return lst

    # ---------------------------------------------------------------- mod & kurulum
    def mode(self) -> str:
        return self.cb_mode.currentData() or "loopback"

    def set_mode(self, mode: str):
        idx = self.cb_mode.findData(mode)
        if idx >= 0:
            self.cb_mode.setCurrentIndex(idx)

    def _on_mode_changed(self):
        is_bb = self.mode() == "ballard"
        self.mode_stack.setCurrentIndex(1 if is_bb else 0)
        self.list_stack.setCurrentIndex(1 if is_bb else 0)
        self.lbl_note.setText(NOTE_BALLARD if is_bb else NOTE_LOOPBACK)
        self._apply_run_state()

    def _sync_bb_enabled(self):
        self.cb_bb_rx_ch.setEnabled(self.chk_bb_tx.isChecked())
        self.cb_bb_tx_ch.setEnabled(self.chk_bb_rx.isChecked())
        self.bb_rx_box.setEnabled(self.chk_bb_rx.isChecked())

    def populate_channels(self, rm):
        for box_map in (self._rx_boxes, self._bb_rx_boxes):
            for cb in box_map.values():
                cb.setParent(None)
            box_map.clear()
        rx = [c for c in rm.channels() if c.startswith("RX")] if rm.is_loaded() else []
        for i, ch in enumerate(rx):
            cb = QCheckBox(f"{ch}  ←  TX")
            cb.setChecked(ch == "RX0")
            self.rx_grid.addWidget(cb, i // 4, i % 4)
            self._rx_boxes[ch] = cb

            cb2 = QCheckBox(f"{ch}  ←  BB")
            cb2.setChecked(ch == "RX0")
            self.bb_rx_grid.addWidget(cb2, i // 4, i % 4)
            self._bb_rx_boxes[ch] = cb2

        has_tb = rm.is_loaded() and rm.has("TB_CTRL")
        self.chk_tb.setEnabled(has_tb)
        self.chk_tb.setChecked(has_tb)
        self.chk_bb_tb.setEnabled(has_tb)
        self.chk_bb_tb.setChecked(has_tb)

    def _scan_ballard(self):
        if self._busy or self._bb_scanning:
            return
        self._bb_scanning = True
        self._apply_run_state()
        self.lbl_bb_status.setText("Ballard cihazları taranıyor…")
        self.app.do_probe_ballard(self._bb_dll_dir)

    def _pick_dll_dir(self):
        d = QFileDialog.getExistingDirectory(
            self, "Ballard BTIDriver DLL klasörünü seç (BTICARD64.DLL / BTI42964.DLL)",
            self._bb_dll_dir or os.path.expanduser("~"),
        )
        if not d:
            return
        self._bb_dll_dir = d
        self.lbl_bb_status.setText(f"DLL klasörü: {d} — taranıyor…")
        self._scan_ballard()

    def set_ballard_probe_result(self, cards: list[CardInfo], dll_path: str = "", error: str = ""):
        self._bb_scanning = False
        self._apply_run_state()
        self._bb_cards = list(cards)
        self.cb_bb_card.blockSignals(True)
        self.cb_bb_card.clear()
        if error:
            self.cb_bb_card.addItem("Kart #0 · Core #0 (manuel)", (0, 0))
            self.lbl_bb_status.setText(f"Uyarı: {error}")
        elif not cards:
            self.cb_bb_card.addItem("Kart #0 · Core #0 (cihaz bulunamadı)", (0, 0))
            self.lbl_bb_status.setText(f"DLL yüklendi ({dll_path}), ancak bağlı ARINC 429 Ballard kartı bulunamadı.")
        else:
            for ci in cards:
                self.cb_bb_card.addItem(ci.display_label(), (ci.card_num, ci.core_num))
            self.lbl_bb_status.setText(f"{len(cards)} Ballard core bulundu · DLL: {os.path.basename(dll_path)}")
        self.cb_bb_card.blockSignals(False)
        self._on_bb_card_changed()

    def _on_bb_card_changed(self):
        idx = self.cb_bb_card.currentIndex()
        if 0 <= idx < len(self._bb_cards):
            ci = self._bb_cards[idx]
            prev_rx = self.cb_bb_rx_ch.currentData()
            prev_tx = self.cb_bb_tx_ch.currentData()
            self.cb_bb_rx_ch.clear()
            for ch in ci.rx_channels:
                self.cb_bb_rx_ch.addItem(f"RX CH{ch}", ch)
            self.cb_bb_tx_ch.clear()
            for ch in ci.tx_channels:
                self.cb_bb_tx_ch.addItem(f"TX CH{ch}", ch)
            if prev_rx in ci.rx_channels:
                self.cb_bb_rx_ch.setCurrentIndex(self.cb_bb_rx_ch.findData(prev_rx))
            if prev_tx in ci.tx_channels:
                self.cb_bb_tx_ch.setCurrentIndex(self.cb_bb_tx_ch.findData(prev_tx))

    def _active_list(self) -> QListWidget:
        return self.lst_bb if self.mode() == "ballard" else self.lst

    def _check_all(self, on: bool):
        lst = self._active_list()
        for i in range(lst.count()):
            it = lst.item(i)
            if it.flags() & Qt.ItemFlag.ItemIsEnabled:
                it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)

    def options(self) -> dict:
        lst = self._active_list()
        sel = [lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lst.count())
               if lst.item(i).checkState() == Qt.CheckState.Checked]
        speeds = tuple(s for s, cb in (("HS", self.chk_hs), ("LS", self.chk_ls)) if cb.isChecked())
        if self.mode() == "ballard":
            card_num, core_num = self.cb_bb_card.currentData() or (0, 0)
            return {
                "mode": "ballard",
                "card_num": int(card_num),
                "core_num": int(core_num),
                "dll_dir": self._bb_dll_dir,
                "test_tx": self.chk_bb_tx.isChecked(),
                "test_rx": self.chk_bb_rx.isChecked(),
                "bb_rx_chan": self.cb_bb_rx_ch.currentData(),
                "bb_tx_chan": self.cb_bb_tx_ch.currentData(),
                "rx": [c for c, cb in self._bb_rx_boxes.items() if cb.isChecked()],
                "tb": self.chk_bb_tb.isChecked(),
                "selected": sel,
                "speeds": speeds or ("HS",),
                "pattern_len": self.sp_pattern.value(),
                "burst_words": self.sp_burst.value(),
                "stop_on_fail": self.chk_stop_fail.isChecked(),
            }
        return {
            "mode": "loopback",
            "rx": [c for c, cb in self._rx_boxes.items() if cb.isChecked()],
            "tb": self.chk_tb.isChecked(),
            "selected": sel,
            "speeds": speeds or ("HS",),
            "pattern_len": self.sp_pattern.value(),
            "burst_words": self.sp_burst.value(),
            "stop_on_fail": self.chk_stop_fail.isChecked(),
        }

    def set_controls(self, can_run: bool, busy: bool, tip: str = ""):
        self._can_run_base = can_run
        self._busy = busy
        self._tip_base = tip
        self._apply_run_state()

    def _apply_run_state(self):
        self.btn_run.setEnabled(self._can_run_base and not self._busy)
        default_tip = (
            "Seçili dış doğrulama testlerini Ballard BusBox / OmniBusBox üzerinden koşar"
            if self.mode() == "ballard"
            else "Seçili testleri TX → RX loopback üzerinden koşar"
        )
        self.btn_run.setToolTip(self._tip_base or default_tip)
        self.btn_stop.setEnabled(self._busy)
        self.cb_mode.setEnabled(not self._busy)
        self.btn_bb_scan.setEnabled(not self._busy and not self._bb_scanning)
        self.btn_bb_dll.setEnabled(not self._busy and not self._bb_scanning)

    # ---------------------------------------------------------------- koşum
    def _run(self):
        o = self.options()
        if o["mode"] == "ballard":
            if not o["test_tx"] and not o["test_rx"]:
                look.confirm(self, "Dış Doğrulama Testi",
                             "En az bir test yönü seçin (Kart TX → Ballard RX veya Ballard TX → Kart RX).",
                             "Tamam", "Kapat")
                return
            if o["test_tx"] and o["bb_rx_chan"] is None:
                look.confirm(self, "Dış Doğrulama Testi", "Ballard RX kanalı seçili değil.", "Tamam", "Kapat")
                return
            if o["test_rx"] and (o["bb_tx_chan"] is None or not o["rx"]):
                look.confirm(self, "Dış Doğrulama Testi",
                             "Ballard TX kanalı ve en az bir Kart RX kanalı seçin.", "Tamam", "Kapat")
                return
        elif not o["rx"] and not o["tb"]:
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
        is_bb = self.report.get("mode") == "ballard"
        prefix = "a429_ballard_test_" if is_bb else "a429_loopback_test_"
        name = os.path.join(d, time.strftime(prefix + "%Y%m%d_%H%M%S.txt"))
        p, flt = QFileDialog.getSaveFileName(self, "Test raporunu kaydet", name, "Metin (*.txt);;JSON (*.json)")
        if not p:
            return
        if p.endswith(".json") or "JSON" in flt:
            text = selftest.report_json(self.report)
        else:
            text = busbox_test.report_text(self.report) if is_bb else selftest.report_text(self.report)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.app.log(f"[Test] Rapor kaydedildi: {p}")


def _label(ch: str) -> str:
    return channel_label(ch)
