"""Test sekmesi: Loopback (selftest.py), Ballard Dış Doğrulama (busbox_test.py) ve AXIL Studio PCS (pcs_test.py)."""
from __future__ import annotations

import json
import os
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QGridLayout, QHBoxLayout, QHeaderView,
    QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit, QProgressBar, QSpinBox, QSplitter,
    QStackedWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import busbox_test, pcs_test, selftest
from ..ballard import CardInfo
from ..pcs_test import PcsInfo
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
NOTE_PCS = (
    "Otonom PCS modu (AXIL Studio cmd_seq · IP 2.1.0): Test programı PCS I-mem'ine bir kez yüklenir ve "
    "FPGA içinde periyodik koşar. PC'den ARINC 429 IP'ye test komutu gönderilmez; yalnızca PCS D-mem sayaçları okunur."
)


class TestTab(QWidget):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.report: dict | None = None
        self._rx_boxes: dict[str, QCheckBox] = {}
        self._bb_rx_boxes: dict[str, QCheckBox] = {}
        self._pcs_rx_boxes: dict[str, QCheckBox] = {}
        self._bb_cards: list[CardInfo] = []
        self._bb_dll_dir: str | None = None
        self._pcs_list: list[PcsInfo] = []
        self._pcs_imem_aw = 9
        self._pcs_dmem_aw = 8
        self._pcs_prev_telem: dict | None = None
        self._pcs_log_count = 0
        self._can_run_base = False
        self._busy = False
        self._bb_scanning = False
        self._pcs_scanning = False
        self._tip_base = ""

        self._pcs_poll_timer = QTimer(self)
        self._pcs_poll_timer.setInterval(1000)
        self._pcs_poll_timer.timeout.connect(self._on_pcs_poll_tick)

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
        self.cb_mode.addItem("Otonom Periyodik Test (AXIL Studio PCS)", "pcs")
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

        # ---- Sayfa 2: Otonom Periyodik Test (AXIL Studio PCS)
        pg_pcs = QWidget()
        l_pcs = QVBoxLayout(pg_pcs)
        l_pcs.setContentsMargins(0, 0, 0, 0)
        l_pcs.setSpacing(6)
        l_pcs.addWidget(look.label(
            "IP 2.1.0 loopback testini AXIL Studio PCS (cmd_seq) bloğuna bir kez yükler; test FPGA içinde "
            "periyodik koşar. PC yalnızca PCS D-mem'den toplam tur ve test/kanal kalma sayaçlarını okur.", "muted", True))

        prow = QHBoxLayout()
        self.cb_pcs = QComboBox()
        self.cb_pcs.addItem("PCS @ 0x00000000 (taranmadı)", 0x00000000)
        self.cb_pcs.currentIndexChanged.connect(self._on_pcs_selected)
        prow.addWidget(self.cb_pcs, 1)
        self.btn_pcs_scan = look.button("Tara", None, self._scan_pcs, "AXIL Studio adres haritasındaki PCS (cmd_seq) bloklarını tara")
        self.btn_pcs_export = look.button(".s Kaydet…", None, self._export_pcs_asm, "Üretilen PCS assembly (.s) dosyasını kaydet")
        prow.addWidget(self.btn_pcs_scan)
        prow.addWidget(self.btn_pcs_export)
        l_pcs.addLayout(prow)

        paddr = QHBoxLayout()
        paddr.addWidget(look.label("PCS Taban Adresi:", "muted"))
        self.ed_pcs_base = QLineEdit("0x00000000")
        self.ed_pcs_base.setToolTip("PCS (cmd_seq) bloğunun 32-bit mutlak AXI taban adresi (hex)")
        paddr.addWidget(self.ed_pcs_base, 1)
        l_pcs.addLayout(paddr)

        self.lbl_pcs_status = look.label("Projedeki PCS bloğunu bulmak için 'Tara' düğmesine basın.", "muted", True)
        l_pcs.addWidget(self.lbl_pcs_status)
        self.lbl_pcs_size = look.label("", "muted")
        l_pcs.addWidget(self.lbl_pcs_size)

        l_pcs.addWidget(look.label("TX'e bağlı RX kanalları (loopback)", "muted"))
        self.pcs_rx_box = QWidget()
        self.pcs_rx_grid = QGridLayout(self.pcs_rx_box)
        self.pcs_rx_grid.setContentsMargins(0, 0, 0, 0)
        self.pcs_rx_grid.setHorizontalSpacing(12)
        l_pcs.addWidget(self.pcs_rx_box)

        self.chk_pcs_tb = QCheckBox("TX BIT (TB) kanalını ve Word Checker'ı dahil et")
        self.chk_pcs_tb.setChecked(True)
        self.chk_pcs_tb.toggled.connect(self._update_pcs_size)
        l_pcs.addWidget(self.chk_pcs_tb)

        pg = QGridLayout()
        pg.setHorizontalSpacing(8)
        pg.setVerticalSpacing(4)
        pg.addWidget(look.label("Tur aralığı (ms)", "muted"), 0, 0)
        self.sp_pcs_gap = QSpinBox()
        self.sp_pcs_gap.setRange(0, 600000)
        self.sp_pcs_gap.setSingleStep(100)
        self.sp_pcs_gap.setValue(500)
        pg.addWidget(self.sp_pcs_gap, 0, 1)

        pg.addWidget(look.label("Maks. tur (0 = sürekli)", "muted"), 1, 0)
        self.sp_pcs_max = QSpinBox()
        self.sp_pcs_max.setRange(0, 1_000_000)
        self.sp_pcs_max.setValue(0)
        pg.addWidget(self.sp_pcs_max, 1, 1)

        pg.addWidget(look.label("Burst (HS / LS Word)", "muted"), 2, 0)
        hb = QHBoxLayout()
        hb.setContentsMargins(0, 0, 0, 0)
        self.sp_pcs_burst_hs = QSpinBox()
        self.sp_pcs_burst_hs.setRange(4, 128)
        self.sp_pcs_burst_hs.setValue(24)
        self.sp_pcs_burst_ls = QSpinBox()
        self.sp_pcs_burst_ls.setRange(4, 64)
        self.sp_pcs_burst_ls.setValue(6)
        hb.addWidget(self.sp_pcs_burst_hs)
        hb.addWidget(self.sp_pcs_burst_ls)
        pg.addLayout(hb, 2, 1)
        l_pcs.addLayout(pg)

        self.chk_pcs_poll = QCheckBox("PCS sayaçlarını otomatik oku (1 s)")
        self.chk_pcs_poll.setChecked(True)
        self.chk_pcs_poll.toggled.connect(self._on_pcs_poll_toggled)
        l_pcs.addWidget(self.chk_pcs_poll)
        self.mode_stack.addWidget(pg_pcs)

        # ---- Ortak ayarlar (Loopback & Ballard için; PCS modunda gizlenir)
        self.common_box = QWidget()
        l_com = QVBoxLayout(self.common_box)
        l_com.setContentsMargins(0, 0, 0, 0)
        l_com.setSpacing(6)
        sp = QHBoxLayout()
        sp.addWidget(look.label("Hızlar:", "muted"))
        self.chk_hs = QCheckBox("High Speed (100 kbps)")
        self.chk_ls = QCheckBox("Low Speed (12.5 kbps)")
        self.chk_hs.setChecked(True)
        self.chk_ls.setChecked(True)
        sp.addWidget(self.chk_hs)
        sp.addWidget(self.chk_ls)
        sp.addStretch(1)
        l_com.addLayout(sp)

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
        l_com.addLayout(g)
        self.chk_stop_fail = QCheckBox("İlk başarısız testte dur")
        l_com.addWidget(self.chk_stop_fail)
        left.lay.addWidget(self.common_box)

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
        self.lst_pcs = self._build_test_list(
            [(tid, title, None, False) for _idx, tid, title, _hint in pcs_test.TESTS],
            (),
        )
        self.lst_pcs.itemChanged.connect(lambda _it: self._update_pcs_size())
        self.list_stack.addWidget(self.lst)
        self.list_stack.addWidget(self.lst_bb)
        self.list_stack.addWidget(self.lst_pcs)
        left.lay.addWidget(self.list_stack, 1)
        left.setMinimumWidth(370)
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
        self.btn_pcs_read = look.button("Oku / Bağlan", None, self._pcs_read_now,
                                        "Çalışan PCS'nin D-mem sayaçlarını ARINC 429 IP'ye dokunmadan okur")
        self.btn_pcs_stop = look.button("PCS Durdur", None, self._pcs_stop, "PCS'deki periyodik testi durdurur")
        self.btn_pcs_clear = look.button("Sayaçları Sıfırla", None, self._pcs_clear,
                                         "PCS toplam tur ve kalma sayaçlarını sıfırlar")
        self.btn_save = look.button("Raporu Kaydet…", None, self._save)
        self.btn_save.setEnabled(False)
        for b in (self.btn_run, self.btn_stop, self.btn_pcs_read, self.btn_pcs_stop, self.btn_pcs_clear, self.btn_save):
            hdr.addWidget(b)
        right.lay.addLayout(hdr)
        self.prog = QProgressBar()
        self.prog.setRange(0, 100)
        self.prog.setValue(0)
        right.lay.addWidget(self.prog)

        # PCS tur sayaçları şeridi (kenarda sabit toplam / hatasız / hatalı tur + canlı hat rozetleri)
        self.pcs_stats_bar = QWidget()
        sbar = QHBoxLayout(self.pcs_stats_bar)
        sbar.setContentsMargins(0, 2, 0, 2)
        sbar.setSpacing(6)
        self.pill_pcs_total = look.Pill("Toplam: 0", "")
        self.pill_pcs_pass = look.Pill("Hatasız: 0", "")
        self.pill_pcs_fail = look.Pill("Hatalı: 0", "")
        self._pcs_ch_pills: list[look.Pill] = []
        self._pcs_ch_bar = QHBoxLayout()
        self._pcs_ch_bar.setContentsMargins(6, 0, 0, 0)
        self._pcs_ch_bar.setSpacing(4)
        self.lbl_pcs_meta = look.label("", "muted")
        sbar.addWidget(self.pill_pcs_total)
        sbar.addWidget(self.pill_pcs_pass)
        sbar.addWidget(self.pill_pcs_fail)
        sbar.addLayout(self._pcs_ch_bar)
        sbar.addStretch(1)
        sbar.addWidget(self.lbl_pcs_meta)
        right.lay.addWidget(self.pcs_stats_bar)

        self.right_split = QSplitter(Qt.Orientation.Vertical)

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
        self.right_split.addWidget(self.tree)

        # PCS canlı hata akışı (log) paneli — geçen testler geri yeşil olur, geçmiş hatalar burada kayıtlı kalır
        self.pcs_log_box = QWidget()
        llay = QVBoxLayout(self.pcs_log_box)
        llay.setContentsMargins(0, 4, 0, 0)
        llay.setSpacing(4)
        lhdr = QHBoxLayout()
        lhdr.setContentsMargins(0, 0, 0, 0)
        lhdr.addWidget(look.label("Hata Akışı (Log)", "muted"))
        self.lbl_pcs_log_cnt = look.label("0 kayıt", "muted")
        lhdr.addWidget(self.lbl_pcs_log_cnt)
        lhdr.addStretch(1)
        self.btn_pcs_log_clear = look.button("Logu Temizle", None, self._clear_pcs_log,
                                             "Alttaki hata akışı kayıtlarını temizler (PCS sayaçlarına dokunmaz)")
        lhdr.addWidget(self.btn_pcs_log_clear)
        llay.addLayout(lhdr)
        self.txt_pcs_log = QPlainTextEdit()
        self.txt_pcs_log.setReadOnly(True)
        self.txt_pcs_log.setFont(look.mono_font(-0.5))
        self.txt_pcs_log.setMaximumBlockCount(2000)
        self.txt_pcs_log.setPlaceholderText(
            "Henüz hata kaydedilmedi — bir test kaldığında tur numarası, hat/kanal adı ve ayrıntısı burada akış halinde tutulur."
        )
        llay.addWidget(self.txt_pcs_log, 1)
        self.right_split.addWidget(self.pcs_log_box)
        self.right_split.setStretchFactor(0, 3)
        self.right_split.setStretchFactor(1, 1)
        self.right_split.setSizes([480, 150])
        right.lay.addWidget(self.right_split, 1)

        self.lbl_note = look.label(NOTE_LOOPBACK, "muted", True)
        right.lay.addWidget(self.lbl_note)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([410, 1000])
        self._on_mode_changed()

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
        m = self.mode()
        idx = {"loopback": 0, "ballard": 1, "pcs": 2}.get(m, 0)
        self.mode_stack.setCurrentIndex(idx)
        self.list_stack.setCurrentIndex(idx)
        self.common_box.setVisible(m != "pcs")
        self.btn_stop.setVisible(m != "pcs")
        self.pcs_stats_bar.setVisible(m == "pcs")
        self.pcs_log_box.setVisible(m == "pcs")
        for b in (self.btn_pcs_read, self.btn_pcs_stop, self.btn_pcs_clear):
            b.setVisible(m == "pcs")
        self.btn_run.setText("▶ PCS'ye Yükle & Başlat" if m == "pcs" else "▶ Testi Başlat")
        self.tree.setHeaderLabels(
            ["Durum", "Test / Kanal", "Kalma · Hat", "Ayrıntı"] if m == "pcs"
            else ["Sonuç", "Test / Kontrol", "Süre", "Ayrıntı"]
        )
        self.lbl_note.setText({"loopback": NOTE_LOOPBACK, "ballard": NOTE_BALLARD, "pcs": NOTE_PCS}[m])
        if m != "pcs":
            self.stop_pcs_poll()
        else:
            self._update_pcs_size()
        self._apply_run_state()

    def _sync_bb_enabled(self):
        self.cb_bb_rx_ch.setEnabled(self.chk_bb_tx.isChecked())
        self.cb_bb_tx_ch.setEnabled(self.chk_bb_rx.isChecked())
        self.bb_rx_box.setEnabled(self.chk_bb_rx.isChecked())

    def populate_channels(self, rm):
        for box_map in (self._rx_boxes, self._bb_rx_boxes, self._pcs_rx_boxes):
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

            cb3 = QCheckBox(f"{ch}  ←  TX")
            cb3.setChecked(ch == "RX0")
            cb3.toggled.connect(self._update_pcs_size)
            self.pcs_rx_grid.addWidget(cb3, i // 4, i % 4)
            self._pcs_rx_boxes[ch] = cb3

        has_tb = rm.is_loaded() and rm.has("TB_CTRL")
        for cb in (self.chk_tb, self.chk_bb_tb, self.chk_pcs_tb):
            cb.setEnabled(has_tb)
            cb.setChecked(has_tb)
        self._update_pcs_size()

    # ---------------------------------------------------------------- Ballard tarama
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

    # ---------------------------------------------------------------- PCS tarama & kontrol
    def pcs_base_addr(self) -> int:
        txt = self.ed_pcs_base.text().strip()
        try:
            return int(txt, 0) & 0xFFFFFFFF
        except ValueError:
            val = self.cb_pcs.currentData()
            return int(val) & 0xFFFFFFFF if val is not None else 0

    def _scan_pcs(self):
        if self._busy or self._pcs_scanning:
            return
        self._pcs_scanning = True
        self._apply_run_state()
        self.lbl_pcs_status.setText("AXIL Studio projesi PCS (cmd_seq) blokları için taranıyor…")
        self.app.do_probe_pcs()

    def set_pcs_probe_result(self, pcs_list: list[PcsInfo], error: str = ""):
        self._pcs_scanning = False
        self._apply_run_state()
        self._pcs_list = list(pcs_list)
        self.cb_pcs.blockSignals(True)
        self.cb_pcs.clear()
        if error:
            self.cb_pcs.addItem("PCS @ 0x00000000 (manuel)", 0)
            self.lbl_pcs_status.setText(f"Uyarı: {error}")
        elif not pcs_list:
            self.cb_pcs.addItem("PCS bulunamadı (adresi elle girin)", 0)
            self.lbl_pcs_status.setText("Adres haritasında cmd_seq bloğu bulunamadı; PCS taban adresini elle girebilirsiniz.")
        else:
            for pi in pcs_list:
                self.cb_pcs.addItem(pi.display_label(), pi.base)
            self.lbl_pcs_status.setText(f"{len(pcs_list)} PCS (cmd_seq) bloğu bulundu.")
        self.cb_pcs.blockSignals(False)
        self._on_pcs_selected()

    def _on_pcs_selected(self):
        idx = self.cb_pcs.currentIndex()
        if 0 <= idx < len(self._pcs_list):
            pi = self._pcs_list[idx]
            self.ed_pcs_base.setText(f"0x{pi.base:08X}")
            self._pcs_imem_aw = pi.imem_aw
            self._pcs_dmem_aw = pi.dmem_aw
            if pi.running_a429:
                self.lbl_pcs_status.setText(
                    f"{pi.name}: A429 periyodik testi zaten koşuyor — 'Oku / Bağlan' ile canlı izleyebilirsiniz."
                )
        self._update_pcs_size()

    def _update_pcs_size(self):
        cap = 1 << self._pcs_imem_aw
        rx = [c for c, cb in self._pcs_rx_boxes.items() if cb.isChecked()]
        tb = self.chk_pcs_tb.isChecked()
        sel = [self.lst_pcs.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.lst_pcs.count())
               if self.lst_pcs.item(i).checkState() == Qt.CheckState.Checked]
        if not sel or (not rx and not tb):
            self.lbl_pcs_size.setText(f"Program boyu: — / {cap} komut (kanal ve test seçin)")
            return
        try:
            ip_base = self.app.rm.base if self.app.rm.is_loaded() else 0x00010000
            clk_hz = int(round((self.app.ci.clk_mhz or 50.0) * 1e6))
            comp = pcs_test.build_program(
                ip_base, rx or ["RX0"], use_tb=tb, selected=sel, clk_hz=clk_hz,
                imem_aw=max(self._pcs_imem_aw, 10), dmem_aw=self._pcs_dmem_aw,
            )
            over = comp.insn_count > cap
            self.lbl_pcs_size.setText(
                f"Program boyu: {comp.insn_count} / {cap} komut ({len(sel)} test)"
                + (" — I-mem kapasitesini aşıyor, test azaltın!" if over else " ✓ sığar")
            )
        except Exception as e:  # noqa: BLE001
            self.lbl_pcs_size.setText(f"Derleme uyarısı: {e}")

    def _export_pcs_asm(self):
        o = self.options()
        if not o["rx"] and not o["tb"]:
            look.confirm(self, "PCS Assembly", "En az bir RX kanalı veya TX BIT seçin.", "Tamam", "Kapat")
            return
        try:
            ip_base = self.app.rm.base if self.app.rm.is_loaded() else 0x00010000
            clk_hz = int(round((self.app.ci.clk_mhz or 50.0) * 1e6))
            comp = pcs_test.build_program(
                ip_base, o["rx"], use_tb=o["tb"], selected=o["selected"], clk_hz=clk_hz,
                gap_ms=o["gap_ms"], max_rounds=o["max_rounds"],
                burst_hs=o["burst_hs"], burst_ls=o["burst_ls"],
                imem_aw=self._pcs_imem_aw, dmem_aw=self._pcs_dmem_aw,
            )
        except Exception as e:  # noqa: BLE001
            look.confirm(self, "PCS Assembly", str(e), "Tamam", "Kapat")
            return
        d = self.app.rs.out_dir or os.path.expanduser("~")
        p, _ = QFileDialog.getSaveFileName(
            self, "PCS Assembly (.s) kaydet", os.path.join(d, "a429_pcs_loopback.s"), "PCS Assembly (*.s);;Tüm Dosyalar (*)"
        )
        if not p:
            return
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(comp.asm)
        self.app.log(f"[PCS] Assembly kaydedildi ({comp.insn_count} komut, SUM 0x{comp.imem_sum:08X}): {p}")

    def start_pcs_poll(self):
        if self.chk_pcs_poll.isChecked() and self.mode() == "pcs":
            self._pcs_poll_timer.start()

    def stop_pcs_poll(self):
        self._pcs_poll_timer.stop()

    def _on_pcs_poll_toggled(self, on: bool):
        if not on:
            self.stop_pcs_poll()
        elif self.mode() == "pcs" and self.report and self.report.get("mode") == "pcs" and self.report.get("pcs_busy"):
            self.start_pcs_poll()

    def _on_pcs_poll_tick(self):
        if self.mode() != "pcs" or not self.app.connected or self._busy:
            return
        self.app.do_pcs_read(self.pcs_base_addr(), quiet=True)

    def _pcs_read_now(self):
        self.app.do_pcs_read(self.pcs_base_addr(), quiet=False)
        self.start_pcs_poll()

    def _pcs_stop(self):
        self.stop_pcs_poll()
        self.app.do_pcs_stop(self.pcs_base_addr())

    def _clear_pcs_ch_pills(self):
        for p in self._pcs_ch_pills:
            self._pcs_ch_bar.removeWidget(p)
            p.setParent(None)
            p.deleteLater()
        self._pcs_ch_pills.clear()

    def _update_pcs_ch_pills(self, items: list[tuple[str, str]]):
        if len(self._pcs_ch_pills) != len(items):
            self._clear_pcs_ch_pills()
            for txt, st in items:
                p = look.Pill(txt, st)
                self._pcs_ch_bar.addWidget(p)
                self._pcs_ch_pills.append(p)
        else:
            for p, (txt, st) in zip(self._pcs_ch_pills, items):
                p.set(txt, st)

    def _clear_pcs_log(self):
        self.txt_pcs_log.clear()
        self._pcs_log_count = 0
        self.lbl_pcs_log_cnt.setText("0 kayıt")

    def _pcs_clear(self):
        self._pcs_prev_telem = None
        self._clear_pcs_log()
        self._clear_pcs_ch_pills()
        self.pill_pcs_total.set("Toplam: 0", "")
        self.pill_pcs_pass.set("Hatasız: 0", "")
        self.pill_pcs_fail.set("Hatalı: 0", "")
        self.app.do_pcs_clear(self.pcs_base_addr())

    def set_pcs_telemetry(self, t: dict | None, error: str = ""):
        if t is None:
            self.pill.set("PCS Hata", "err")
            self.lbl_time.setText(error)
            return

        prev = self._pcs_prev_telem
        if prev is not None and (
            t["total_rounds"] < prev.get("total_rounds", 0)
            or t["pcs_base"] != prev.get("pcs_base")
        ):
            prev = None
            self._clear_pcs_log()

        events = pcs_test.diff_fail_events(prev, t)
        if events:
            for line in events:
                self.txt_pcs_log.appendPlainText(line)
            self._pcs_log_count += len(events)
            self.lbl_pcs_log_cnt.setText(f"{self._pcs_log_count} kayıt")

        prev_ch_fails = {c["code"]: int(c["fails"]) for c in prev.get("channels", [])} if prev else {}
        self._pcs_prev_telem = t

        self.report = t
        self.btn_save.setEnabled(True)
        self.tree.clear()

        last_bad = bool(t.get("last_round_failed", any(x.get("last_failed") for x in t["tests"])))
        cur_bad_chans = {
            ch for x in t["tests"] if x.get("last_failed")
            for ch in (x.get("fail_channels") or ())
        }

        if t["pcs_err"]:
            self.pill.set(f"PCS HATA ({t['pcs_err_text']})", "err")
            self.stop_pcs_poll()
        elif not t["recognized"]:
            self.pill.set("A429 PCS Programı Yüklü Değil", "warn")
        elif t["run_state"] == "TAMAMLANDI":
            ok = t["total_rounds"] > 0 and not last_bad
            self.pill.set(
                f"TAMAMLANDI {'✓' if ok else '✗'} ({t['total_rounds']} tur, {t['pass_rounds']} hatasız / {t['fail_rounds']} hatalı)",
                "ok" if ok else "err",
            )
            self.stop_pcs_poll()
        elif t["pcs_busy"]:
            if t["total_rounds"] == 0:
                self.pill.set("KOŞUYOR · 0 tur", "accent")
            elif not last_bad:
                self.pill.set(f"KOŞUYOR · {t['total_rounds']} tur · GEÇTİ ✓", "ok")
            else:
                self.pill.set(f"KOŞUYOR · {t['total_rounds']} tur · SON TUR KALDI ✗", "err")
        else:
            self.pill.set(f"DURDURULDU · {t['total_rounds']} tur ({t['fail_rounds']} hatalı)", "warn")
            self.stop_pcs_poll()

        # Kenarda sabit toplam / hatasız / hatalı tur sayaçları + canlı hat rozetleri
        self.pill_pcs_total.set(f"Toplam: {t['total_rounds']}", "")
        self.pill_pcs_pass.set(f"Hatasız: {t['pass_rounds']}", "ok" if t["pass_rounds"] else "")
        self.pill_pcs_fail.set(f"Hatalı: {t['fail_rounds']}", "err" if t["fail_rounds"] else "")
        ch_pill_items: list[tuple[str, str]] = []
        for c in t["channels"]:
            ch_now = (c["name"] in cur_bad_chans) or (last_bad and c["fails"] > prev_ch_fails.get(c["code"], 0))
            if t["total_rounds"] == 0:
                ch_pill_items.append((f"{c['name']}: —", ""))
            elif ch_now:
                ch_pill_items.append((f"{c['name']} ✗ ({c['fails']})", "err"))
            else:
                ch_pill_items.append((f"{c['name']} ✓ ({c['fails']})", "ok"))
        self._update_pcs_ch_pills(ch_pill_items)

        meta = (
            f"Son tur: {t['last_dur_ms']} ms · Gürültü maks: {t['max_noise_clk']} clk · "
            f"PCS: {t['pcs_state']} (PC={t['pcs_pc']}, {t['imem_cnt']}/{t['imem_size']} komut)"
        )
        self.lbl_pcs_meta.setText(meta)
        self.lbl_time.setText("")

        if t["max_rounds"] > 0:
            self.prog.setMaximum(t["max_rounds"])
            self.prog.setValue(min(t["total_rounds"], t["max_rounds"]))
            self.prog.setFormat(f"%v / %m tur  ·  {t['pass_rounds']} hatasız, {t['fail_rounds']} hatalı")
        else:
            self.prog.setMaximum(100)
            self.prog.setValue(100 if t["total_rounds"] else 0)
            self.prog.setFormat(f"Sürekli  ·  {t['total_rounds']} tur ({t['pass_rounds']} hatasız, {t['fail_rounds']} hatalı)")

        # Ağaç satırları: 1) Özet, 2) Test bazlı (son tura göre yeşil/kırmızı + hat), 3) Kanal bazlı, 4) İlk/Son hata
        summary_it = QTreeWidgetItem([
            "ÖZET",
            f"Toplam {t['total_rounds']} tur · Hatasız {t['pass_rounds']} · Hatalı {t['fail_rounds']}",
            f"{t['fail_rounds']}/{t['total_rounds']}",
            f"PCS 0x{t['pcs_base']:08X} → IP 0x{t['ip_base']:08X} · aralık {t['gap_ms']} ms · maks. gürültü {t['max_noise_clk']} clk",
        ])
        f = summary_it.font(0)
        f.setBold(True)
        summary_it.setFont(0, f)
        self.tree.addTopLevelItem(summary_it)

        for x in t["tests"]:
            cur_failed = bool(x["last_failed"])
            had_fails = x["fails"] > 0
            fch = x.get("fail_channels") or []
            hat_txt = ", ".join(fch)
            cnt_txt = f"{x['fails']} / {t['total_rounds']}" + (f" · {hat_txt}" if hat_txt else "")
            if t["total_rounds"] == 0:
                st_txt, col = "BEKLİYOR", look.color("muted")
                detail = "ilk tur bekleniyor"
            elif cur_failed:
                st_txt, col = "KALDI", look.color("danger")
                prefix = f"[Hat: {hat_txt}] " if hat_txt else ""
                detail = f"{prefix}Son turda KALDI · {x['hint']}"
            else:
                st_txt, col = "GEÇTİ", look.color("success")
                if had_fails:
                    hat_part = f" · son hat: {hat_txt}" if hat_txt else ""
                    detail = f"Son tur GEÇTİ (geçmişte {x['fails']} hata{hat_part})"
                else:
                    detail = "0 hata"
            it = QTreeWidgetItem([st_txt, x["title"], cnt_txt, detail])
            it.setForeground(0, QBrush(col))
            if cur_failed:
                it.setForeground(2, QBrush(look.color("danger")))
            elif had_fails:
                it.setForeground(2, QBrush(look.color("warning")))
            ff = it.font(0)
            ff.setBold(True)
            it.setFont(0, ff)
            self.tree.addTopLevelItem(it)

        if t["channels"]:
            ch_top = QTreeWidgetItem([
                "KANAL",
                "Hat / Kanal Bazlı Kalma Sayaçları",
                f"{sum(c['fails'] for c in t['channels'])} hata",
                ", ".join(f"{c['name']}: {c['fails']}" for c in t["channels"]),
            ])
            for c in t["channels"]:
                ch_now = (c["name"] in cur_bad_chans) or (last_bad and c["fails"] > prev_ch_fails.get(c["code"], 0))
                if ch_now:
                    c_mark, c_col, c_det = "✗", look.color("danger"), "son turda hata!"
                elif c["fails"] > 0:
                    c_mark, c_col, c_det = "✓", look.color("success"), f"son tur temiz (geçmişte {c['fails']} hata)"
                else:
                    c_mark, c_col, c_det = "✓", look.color("success"), "temiz"
                cit = QTreeWidgetItem([c_mark, c["name"], str(c["fails"]), c_det])
                cit.setForeground(0, QBrush(c_col))
                if ch_now:
                    cit.setForeground(2, QBrush(look.color("danger")))
                elif c["fails"] > 0:
                    cit.setForeground(2, QBrush(look.color("warning")))
                ch_top.addChild(cit)
            self.tree.addTopLevelItem(ch_top)
            ch_top.setExpanded(True)

        if t["first_fail"]:
            ff = t["first_fail"]
            fit = QTreeWidgetItem([
                "İLK HATA",
                f"Tur #{ff['round']} · [Hat: {ff['channel']}] · {ff['test_title']}",
                f"Kod {ff['sub_code']}",
                f"{ff['reason']} (beklenen 0x{ff['expected']:08X}, okunan 0x{ff['got']:08X})",
            ])
            fcol = look.color("danger" if last_bad else "warning")
            fit.setForeground(0, QBrush(fcol))
            self.tree.addTopLevelItem(fit)

        lf = t.get("last_fail")
        if lf and lf != t.get("first_fail"):
            lit = QTreeWidgetItem([
                "SON HATA",
                f"Tur #{lf['round']} · [Hat: {lf['channel']}] · {lf['test_title']}",
                f"Kod {lf['sub_code']}",
                f"{lf['reason']} (beklenen 0x{lf['expected']:08X}, okunan 0x{lf['got']:08X})",
            ])
            lcol = look.color("danger" if last_bad else "warning")
            lit.setForeground(0, QBrush(lcol))
            self.tree.addTopLevelItem(lit)

        if t["pcs_err"]:
            eit = QTreeWidgetItem([
                "PCS HATA",
                t["pcs_err_text"],
                f"PC={t['pcs_pc']}",
                f"ERR_CODE={t['pcs_err_code']} ERR_PC={t['pcs_err_pc']} ERR_ADDR=0x{t['pcs_err_addr']:08X}",
            ])
            eit.setForeground(0, QBrush(look.color("danger")))
            self.tree.addTopLevelItem(eit)

    # ---------------------------------------------------------------- ortak liste & seçenekler
    def _active_list(self) -> QListWidget:
        m = self.mode()
        if m == "ballard":
            return self.lst_bb
        if m == "pcs":
            return self.lst_pcs
        return self.lst

    def _check_all(self, on: bool):
        lst = self._active_list()
        lst.blockSignals(True)
        for i in range(lst.count()):
            it = lst.item(i)
            if it.flags() & Qt.ItemFlag.ItemIsEnabled:
                it.setCheckState(Qt.CheckState.Checked if on else Qt.CheckState.Unchecked)
        lst.blockSignals(False)
        if self.mode() == "pcs":
            self._update_pcs_size()

    def options(self) -> dict:
        lst = self._active_list()
        sel = [lst.item(i).data(Qt.ItemDataRole.UserRole) for i in range(lst.count())
               if lst.item(i).checkState() == Qt.CheckState.Checked]
        speeds = tuple(s for s, cb in (("HS", self.chk_hs), ("LS", self.chk_ls)) if cb.isChecked())
        m = self.mode()
        if m == "pcs":
            return {
                "mode": "pcs",
                "pcs_base": self.pcs_base_addr(),
                "imem_aw": self._pcs_imem_aw,
                "dmem_aw": self._pcs_dmem_aw,
                "rx": [c for c, cb in self._pcs_rx_boxes.items() if cb.isChecked()],
                "tb": self.chk_pcs_tb.isChecked(),
                "selected": sel,
                "gap_ms": self.sp_pcs_gap.value(),
                "max_rounds": self.sp_pcs_max.value(),
                "burst_hs": self.sp_pcs_burst_hs.value(),
                "burst_ls": self.sp_pcs_burst_ls.value(),
            }
        if m == "ballard":
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
        m = self.mode()
        self.btn_run.setEnabled(self._can_run_base and not self._busy)
        default_tip = {
            "ballard": "Seçili dış doğrulama testlerini Ballard BusBox / OmniBusBox üzerinden koşar",
            "pcs": "Seçili IP 2.1.0 loopback testlerini PCS I-mem'e yükler ve FPGA içinde otonom başlatır",
            "loopback": "Seçili testleri TX → RX loopback üzerinden koşar",
        }[m]
        self.btn_run.setToolTip(self._tip_base or default_tip)
        self.btn_stop.setEnabled(self._busy)
        self.cb_mode.setEnabled(not self._busy)
        self.btn_bb_scan.setEnabled(not self._busy and not self._bb_scanning)
        self.btn_bb_dll.setEnabled(not self._busy and not self._bb_scanning)
        pcs_ok = self._can_run_base and not self._busy
        self.btn_pcs_scan.setEnabled(pcs_ok and not self._pcs_scanning)
        self.btn_pcs_read.setEnabled(pcs_ok)
        self.btn_pcs_stop.setEnabled(pcs_ok)
        self.btn_pcs_clear.setEnabled(pcs_ok)

    # ---------------------------------------------------------------- koşum
    def _run(self):
        o = self.options()
        if o["mode"] == "pcs":
            if not o["rx"] and not o["tb"]:
                look.confirm(self, "Otonom PCS Testi", "En az bir RX kanalı ya da TX BIT seçin.", "Tamam", "Kapat")
                return
            if not o["selected"]:
                look.confirm(self, "Otonom PCS Testi", "En az bir test seçin.", "Tamam", "Kapat")
                return
            self.tree.clear()
            self.report = None
            self._pcs_prev_telem = None
            self._clear_pcs_log()
            self._clear_pcs_ch_pills()
            self.pill_pcs_total.set("Toplam: 0", "")
            self.pill_pcs_pass.set("Hatasız: 0", "")
            self.pill_pcs_fail.set("Hatalı: 0", "")
            self.lbl_pcs_meta.setText("")
            self.btn_save.setEnabled(False)
            self.pill.set("PCS'ye yükleniyor…", "accent")
            self.lbl_time.setText("")
            self.prog.setValue(0)
            self.app.do_pcs_load_start(o)
            return
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
        rmode = self.report.get("mode")
        prefix = {"ballard": "a429_ballard_test_", "pcs": "a429_pcs_test_"}.get(rmode, "a429_loopback_test_")
        name = os.path.join(d, time.strftime(prefix + "%Y%m%d_%H%M%S.txt"))
        p, flt = QFileDialog.getSaveFileName(self, "Test raporunu kaydet", name, "Metin (*.txt);;JSON (*.json)")
        if not p:
            return
        if p.endswith(".json") or "JSON" in flt:
            text = pcs_test.report_json(self.report) if rmode == "pcs" else selftest.report_json(self.report)
        else:
            text = (
                pcs_test.report_text(self.report) if rmode == "pcs"
                else (busbox_test.report_text(self.report) if rmode == "ballard" else selftest.report_text(self.report))
            )
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.app.log(f"[Test] Rapor kaydedildi: {p}")


def _label(ch: str) -> str:
    return channel_label(ch)
