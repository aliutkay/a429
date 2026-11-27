"""Test sekmesi: Loopback (selftest.py), Ballard Dış Doğrulama (busbox_test.py) ve AXIL Studio PCS (pcs_test.py)."""
from __future__ import annotations

import json
import os
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QBrush, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QGridLayout,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPlainTextEdit,
    QProgressBar, QSpinBox, QSplitter, QStackedWidget, QTextBrowser, QToolButton, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import busbox_test, pcs_test, selftest, test_docs
from ..ballard import CardInfo
from ..pcs_test import PcsInfo
from ..regs import channel_label
from . import look

STATUS_STYLE = {
    "PASS": ("GEÇTİ", "success"),
    "FAIL": ("KALDI", "danger"),
    "ERROR": ("HATA", "danger"),
    "SKIP": ("ATLANDI", "muted"),
}

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
    "FPGA içinde periyodik koşar. PC yalnızca PCS D-mem sayaçlarını okur; 'İlk hatada durdur' açıkken RX RAM "
    "inceleme için korunur."
)


class TestInfoDialog(QDialog):
    """Seçili testin ne yaptığını, neyi kontrol ettiğini ve olası kök nedenlerini gösteren bilgi penceresi."""

    def __init__(self, parent, doc: test_docs.TestDoc, fail_detail: str = ""):
        super().__init__(parent)
        self.setWindowTitle(f"Test Bilgisi — {doc.title}")
        self.resize(580, 380)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(10)
        view = QTextBrowser()
        view.setOpenExternalLinks(False)
        view.setHtml(test_docs.format_test_info_html(doc, fail_detail=fail_detail))
        lay.addWidget(view, 1)
        row = QHBoxLayout()
        row.addStretch(1)
        btn = look.button("Kapat", "primary", self.accept)
        row.addWidget(btn)
        lay.addLayout(row)


def _info_btn(callback, tip: str = "Bu testin açıklamasını ve olası hata nedenlerini göster") -> QToolButton:
    b = QToolButton()
    b.setText("ⓘ")
    b.setToolTip(tip)
    b.setAutoRaise(True)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFixedSize(24, 22)
    b.clicked.connect(callback)
    return b


def _fmt_duration(secs: float) -> str:
    s = max(0, int(secs))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{sec:02d}"
    return f"{m:02d}:{sec:02d}"


class TestTab(QWidget):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self._reports: dict[str, dict | None] = {"loopback": None, "ballard": None, "pcs": None}
        self._pill_state: dict[str, tuple[str, str, str]] = {
            "loopback": ("Koşulmadı", "", ""),
            "ballard": ("Koşulmadı", "", ""),
            "pcs": ("Koşulmadı", "", ""),
        }
        self._rx_boxes: dict[str, QCheckBox] = {}
        self._bb_rx_boxes: dict[str, QCheckBox] = {}
        self._pcs_rx_boxes: dict[str, QCheckBox] = {}
        self._bb_cards: list[CardInfo] = []
        self._bb_dll_dir: str | None = None
        self._pcs_list: list[PcsInfo] = []
        self._pcs_imem_aw = 10
        self._pcs_dmem_aw = 8
        self._pcs_prev_telem: dict | None = None
        self._pcs_log_entries: list[tuple[str, str]] = []
        self._pcs_started_ts: float | None = None
        self._pcs_last_fail_ch: str = ""
        self._can_run_base = False
        self._busy = False
        self._bb_scanning = False
        self._pcs_scanning = False
        self._tip_base = ""
        self._active_run_mode: str | None = None

        self._pcs_poll_timer = QTimer(self)
        self._pcs_poll_timer.setInterval(1000)
        self._pcs_poll_timer.timeout.connect(self._on_pcs_poll_tick)

        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split)

        # ================================================================ Sol: kurulum
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
            "bağlayın. TX BIT kanalı TX hattını kart üzerindeki kendi alıcısıyla dinler.", "muted", True))
        l_lb.addLayout(self._rx_header_row("TX'e bağlı RX kanalları", self._rx_boxes))
        self.rx_box = QWidget()
        self.rx_grid = QGridLayout(self.rx_box)
        self.rx_grid.setContentsMargins(0, 0, 0, 0)
        self.rx_grid.setHorizontalSpacing(10)
        self.rx_grid.setVerticalSpacing(4)
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

        l_bb.addLayout(self._rx_header_row("Ballard TX'e bağlı Kart RX kanalları", self._bb_rx_boxes))
        self.bb_rx_box = QWidget()
        self.bb_rx_grid = QGridLayout(self.bb_rx_box)
        self.bb_rx_grid.setContentsMargins(0, 0, 0, 0)
        self.bb_rx_grid.setHorizontalSpacing(10)
        self.bb_rx_grid.setVerticalSpacing(4)
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
            "IP 2.1.0 loopback testini AXIL Studio PCS (cmd_seq) bloğuna yükler; test FPGA içinde "
            "periyodik koşar. PC yalnızca PCS D-mem sayaçlarını okur.", "muted", True))

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

        l_pcs.addLayout(self._rx_header_row("TX'e bağlı RX kanalları (loopback)", self._pcs_rx_boxes, on_change=self._update_pcs_size))
        self.pcs_rx_box = QWidget()
        self.pcs_rx_grid = QGridLayout(self.pcs_rx_box)
        self.pcs_rx_grid.setContentsMargins(0, 0, 0, 0)
        self.pcs_rx_grid.setHorizontalSpacing(10)
        self.pcs_rx_grid.setVerticalSpacing(4)
        l_pcs.addWidget(self.pcs_rx_box)

        self.chk_pcs_tb = QCheckBox("TX BIT (TB) kanalını ve Word Checker'ı dahil et")
        self.chk_pcs_tb.setChecked(True)
        self.chk_pcs_tb.toggled.connect(self._update_pcs_size)
        l_pcs.addWidget(self.chk_pcs_tb)

        pg = QGridLayout()
        pg.setHorizontalSpacing(8)
        pg.setVerticalSpacing(4)
        pg.addWidget(look.label("Tur aralığı (ms)", "muted"), 0, 0)
        gap_row = QHBoxLayout()
        gap_row.setContentsMargins(0, 0, 0, 0)
        gap_row.setSpacing(4)
        self.sp_pcs_gap = QSpinBox()
        self.sp_pcs_gap.setRange(0, 600000)
        self.sp_pcs_gap.setSingleStep(100)
        self.sp_pcs_gap.setValue(500)
        self.btn_pcs_gap_apply = look.button(
            "Uygula", None, self._pcs_apply_gap,
            "Tur aralığını programı yeniden yüklemeden çalışan PCS'ye canlı uygular",
        )
        gap_row.addWidget(self.sp_pcs_gap, 1)
        gap_row.addWidget(self.btn_pcs_gap_apply)
        pg.addLayout(gap_row, 0, 1)

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

        self.chk_pcs_stop_fail = QCheckBox("İlk hatada testi durdur (Okunan Veriler'de inceleme için)")
        self.chk_pcs_stop_fail.setToolTip(
            "Açıkken ilk kalan testin sonunda PCS durur (HATA İLE DURDU); kalan testler koşmaz ve "
            "RX Word/Error/BitDiag RAM verileri bozulmadan 'Okunan Veriler' sekmesinde incelenebilir."
        )
        self.chk_pcs_stop_fail.toggled.connect(self._on_pcs_stop_fail_toggled)
        l_pcs.addWidget(self.chk_pcs_stop_fail)

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
        self.btn_list_info = look.button("ⓘ Bilgi", None, self._show_selected_list_info,
                                         "Listede seçili testin ne yaptığını ve olası kök nedenlerini gösterir")
        th.addWidget(self.btn_list_info)
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
        left.setMinimumWidth(385)
        split.addWidget(left)

        # ================================================================ Sağ: moda özel sonuç sayfaları
        right = look.Card(margins=12, spacing=8, object_name="SubCard")

        # Üst başlık + aksiyon çubuğu
        hdr = QHBoxLayout()
        self.lbl_res_title = look.label("Loopback Test Sonuçları", "cardTitle")
        hdr.addWidget(self.lbl_res_title)
        self.pill = look.Pill("Koşulmadı", "")
        hdr.addWidget(self.pill)
        self.lbl_time = look.label("", "muted")
        hdr.addWidget(self.lbl_time)
        hdr.addStretch(1)

        self.btn_run = look.button("▶ Testi Başlat", "primary", self._run)
        self.btn_stop = look.button("Durdur", None, app.do_stop)
        self.btn_pcs_start = look.button(
            "▶ PCS Başlat", None, self._pcs_start,
            "Yüklü PCS testini I-mem'i yeniden yüklemeden başlatır veya 'HATA İLE DURDU' durumundan sürdürür",
        )
        self.btn_pcs_stop = look.button("⏸ PCS Durdur", None, self._pcs_stop, "PCS'deki periyodik testi durdurur")
        self.btn_pcs_read = look.button(
            "Oku / Bağlan", None, self._pcs_read_now,
            "Çalışan PCS'nin D-mem sayaçlarını ARINC 429 IP'ye dokunmadan okur",
        )
        self.btn_pcs_clear = look.button(
            "Sayaçları Sıfırla", None, self._pcs_clear,
            "PCS toplam tur ve kalma sayaçlarını sıfırlar",
        )
        self.btn_pcs_inspect = look.button(
            "Okunan Veriler'de İncele →", None, self._pcs_inspect_fail,
            "Hata veren RX/TB kanalını seçip Okunan Veriler sekmesinde Word/Error/BitDiag RAM verilerini okur",
        )
        self.btn_pcs_inspect.setEnabled(False)
        self.btn_save = look.button("Raporu Kaydet…", None, self._save)
        self.btn_save.setEnabled(False)

        for b in (
            self.btn_run, self.btn_stop, self.btn_pcs_start, self.btn_pcs_stop,
            self.btn_pcs_read, self.btn_pcs_clear, self.btn_pcs_inspect, self.btn_save,
        ):
            hdr.addWidget(b)
        right.lay.addLayout(hdr)

        self.prog = QProgressBar()
        self.prog.setRange(0, 100)
        self.prog.setValue(0)
        right.lay.addWidget(self.prog)

        # ---- Moda özel 3 bağımsız sonuç sayfası
        self.result_stack = QStackedWidget()
        right.lay.addWidget(self.result_stack, 1)

        # === Sayfa 0: Loopback Sonuçları ===
        pg_res_lb = QWidget()
        rl_lb = QVBoxLayout(pg_res_lb)
        rl_lb.setContentsMargins(0, 0, 0, 0)
        rl_lb.setSpacing(6)
        lb_bar = QHBoxLayout()
        lb_bar.setSpacing(6)
        self.pill_lb_pass = look.Pill("Geçen: 0", "")
        self.pill_lb_fail = look.Pill("Kalan: 0", "")
        self.pill_lb_skip = look.Pill("Atlanan: 0", "")
        self.lbl_lb_meta = look.label("Loopback testi başlatıldığında sonuçlar burada görüntülenir.", "muted")
        for w in (self.pill_lb_pass, self.pill_lb_fail, self.pill_lb_skip):
            lb_bar.addWidget(w)
        lb_bar.addSpacing(8)
        lb_bar.addWidget(self.lbl_lb_meta, 1)
        rl_lb.addLayout(lb_bar)
        self.tree_lb = self._build_result_tree(["Sonuç", "Test / Kontrol", "Hız", "Süre", "Ayrıntı", "ⓘ"])
        rl_lb.addWidget(self.tree_lb, 1)
        self.result_stack.addWidget(pg_res_lb)

        # === Sayfa 1: Ballard Dış Doğrulama Sonuçları ===
        pg_res_bb = QWidget()
        rl_bb = QVBoxLayout(pg_res_bb)
        rl_bb.setContentsMargins(0, 0, 0, 0)
        rl_bb.setSpacing(6)
        bb_bar = QHBoxLayout()
        bb_bar.setSpacing(6)
        self.pill_bb_pass = look.Pill("Geçen: 0", "")
        self.pill_bb_fail = look.Pill("Kalan: 0", "")
        self.pill_bb_tx = look.Pill("Kart TX → BB RX: —", "")
        self.pill_bb_rx = look.Pill("BB TX → Kart RX: —", "")
        self.lbl_bb_meta = look.label("Ballard dış doğrulama sonuçları burada görüntülenir.", "muted")
        for w in (self.pill_bb_pass, self.pill_bb_fail, self.pill_bb_tx, self.pill_bb_rx):
            bb_bar.addWidget(w)
        bb_bar.addSpacing(8)
        bb_bar.addWidget(self.lbl_bb_meta, 1)
        rl_bb.addLayout(bb_bar)
        self.tree_bb = self._build_result_tree(["Sonuç", "Test / Kontrol", "Hız", "Süre", "Ayrıntı", "ⓘ"])
        rl_bb.addWidget(self.tree_bb, 1)
        self.result_stack.addWidget(pg_res_bb)

        # === Sayfa 2: Otonom Periyodik PCS Sonuçları ===
        pg_res_pcs = QWidget()
        rl_pcs = QVBoxLayout(pg_res_pcs)
        rl_pcs.setContentsMargins(0, 0, 0, 0)
        rl_pcs.setSpacing(6)

        # Özet sayaç şeridi (Toplam / Hatasız / Hatalı / Başarı % / Seri / Süre)
        self.pcs_stats_bar = QWidget()
        sbar = QHBoxLayout(self.pcs_stats_bar)
        sbar.setContentsMargins(0, 2, 0, 0)
        sbar.setSpacing(6)
        self.pill_pcs_total = look.Pill("Toplam: 0", "")
        self.pill_pcs_pass = look.Pill("Hatasız: 0", "")
        self.pill_pcs_fail = look.Pill("Hatalı: 0", "")
        self.pill_pcs_rate = look.Pill("Başarı: —", "")
        self.pill_pcs_streak = look.Pill("Seri: 0", "")
        self.pill_pcs_uptime = look.Pill("Süre: 00:00", "")
        self.lbl_pcs_meta = look.label("", "muted")
        for p in (
            self.pill_pcs_total, self.pill_pcs_pass, self.pill_pcs_fail,
            self.pill_pcs_rate, self.pill_pcs_streak, self.pill_pcs_uptime,
        ):
            sbar.addWidget(p)
        sbar.addStretch(1)
        sbar.addWidget(self.lbl_pcs_meta)
        rl_pcs.addWidget(self.pcs_stats_bar)

        # Çoklu-RX uyumlu canlı hat rozet şeridi (6 rozet/satır sarmalı)
        self._pcs_ch_pills: list[look.Pill] = []
        self._pcs_ch_wrap = QWidget()
        self._pcs_ch_grid = QGridLayout(self._pcs_ch_wrap)
        self._pcs_ch_grid.setContentsMargins(0, 0, 0, 0)
        self._pcs_ch_grid.setHorizontalSpacing(6)
        self._pcs_ch_grid.setVerticalSpacing(4)
        self._pcs_ch_wrap.setVisible(False)
        rl_pcs.addWidget(self._pcs_ch_wrap)

        self.right_split = QSplitter(Qt.Orientation.Vertical)

        # Üst: yalnızca test satırlarını gösteren temiz PCS tablosu
        self.pcs_tree = QTreeWidget()
        self.pcs_tree.setColumnCount(6)
        self.pcs_tree.setHeaderLabels(["Son Tur", "Test Adı", "Hatalı / Toplam", "Kalan Hat(lar)", "Ayrıntı", "ⓘ"])
        self.pcs_tree.setRootIsDecorated(False)
        self.pcs_tree.setAlternatingRowColors(True)
        self.pcs_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        ph = self.pcs_tree.header()
        ph.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        ph.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        ph.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        ph.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        ph.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        ph.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        self.pcs_tree.setColumnWidth(1, 310)
        self.pcs_tree.setColumnWidth(5, 34)
        self.right_split.addWidget(self.pcs_tree)

        # Orta: Hat / Kanal Durumu + İlk/Son Hata Özeti (yan yana kompakt)
        mid_box = QWidget()
        mlay = QHBoxLayout(mid_box)
        mlay.setContentsMargins(0, 2, 0, 2)
        mlay.setSpacing(8)

        ch_panel = QFrame()
        ch_panel.setObjectName("SubPanel")
        cpl = QVBoxLayout(ch_panel)
        cpl.setContentsMargins(8, 6, 8, 6)
        cpl.setSpacing(4)
        cpl.addWidget(look.label("Hat / Kanal Durumu", "cardTitle"))
        self.pcs_ch_tree = QTreeWidget()
        self.pcs_ch_tree.setColumnCount(4)
        self.pcs_ch_tree.setHeaderLabels(["Durum", "Hat / Kanal", "Toplam Hata", "Son Tur"])
        self.pcs_ch_tree.setRootIsDecorated(False)
        self.pcs_ch_tree.setAlternatingRowColors(True)
        chh = self.pcs_ch_tree.header()
        chh.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        chh.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        chh.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        chh.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        cpl.addWidget(self.pcs_ch_tree, 1)
        mlay.addWidget(ch_panel, 1)

        fail_panel = QFrame()
        fail_panel.setObjectName("SubPanel")
        fpl = QVBoxLayout(fail_panel)
        fpl.setContentsMargins(8, 6, 8, 6)
        fpl.setSpacing(4)
        fpl.addWidget(look.label("Yakalanan Hata Özeti (İlk / Son)", "cardTitle"))
        self.lbl_pcs_fail_summary = QLabel("Henüz hata kaydedilmedi — tüm turlar temiz.")
        self.lbl_pcs_fail_summary.setWordWrap(True)
        self.lbl_pcs_fail_summary.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.lbl_pcs_fail_summary.setFont(look.mono_font(-0.5))
        fpl.addWidget(self.lbl_pcs_fail_summary, 1)
        mlay.addWidget(fail_panel, 1)
        self.right_split.addWidget(mid_box)

        # Alt: Renkli + Hat Filtreli Hata Akışı (Log)
        self.pcs_log_box = QWidget()
        llay = QVBoxLayout(self.pcs_log_box)
        llay.setContentsMargins(0, 2, 0, 0)
        llay.setSpacing(4)
        lhdr = QHBoxLayout()
        lhdr.setContentsMargins(0, 0, 0, 0)
        lhdr.addWidget(look.label("Hata ve Durum Akışı (Log)", "cardTitle"))
        self.lbl_pcs_log_cnt = look.label("0 kayıt", "muted")
        lhdr.addWidget(self.lbl_pcs_log_cnt)
        lhdr.addSpacing(8)
        lhdr.addWidget(look.label("Hat Filtresi:", "muted"))
        self.cb_pcs_log_filter = QComboBox()
        self.cb_pcs_log_filter.addItem("Tüm Hatlar", "")
        self.cb_pcs_log_filter.currentIndexChanged.connect(self._rerender_pcs_log)
        lhdr.addWidget(self.cb_pcs_log_filter)
        lhdr.addStretch(1)
        self.btn_pcs_log_save = look.button("Logu Kaydet…", None, self._save_pcs_log,
                                            "Hata akışı kayıtlarını .txt dosyasına kaydeder")
        self.btn_pcs_log_clear = look.button("Logu Temizle", None, self._clear_pcs_log,
                                             "Alttaki hata akışı kayıtlarını temizler (PCS sayaçlarına dokunmaz)")
        lhdr.addWidget(self.btn_pcs_log_save)
        lhdr.addWidget(self.btn_pcs_log_clear)
        llay.addLayout(lhdr)
        self.txt_pcs_log = QPlainTextEdit()
        self.txt_pcs_log.setReadOnly(True)
        self.txt_pcs_log.setFont(look.mono_font(-0.5))
        self.txt_pcs_log.setMaximumBlockCount(3000)
        self.txt_pcs_log.setPlaceholderText(
            "Henüz hata kaydedilmedi — bir test kaldığında kırmızı, toparlandığında yeşil, durduğunda turuncu renkte burada listelenir."
        )
        llay.addWidget(self.txt_pcs_log, 1)
        self.right_split.addWidget(self.pcs_log_box)
        self.right_split.setStretchFactor(0, 4)
        self.right_split.setStretchFactor(1, 2)
        self.right_split.setStretchFactor(2, 2)
        self.right_split.setSizes([340, 120, 160])
        rl_pcs.addWidget(self.right_split, 1)
        self.result_stack.addWidget(pg_res_pcs)

        self.lbl_note = look.label(NOTE_LOOPBACK, "muted", True)
        right.lay.addWidget(self.lbl_note)
        split.addWidget(right)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([420, 1020])
        self._on_mode_changed()

    # ---------------------------------------------------------------- geriye dönük uyumlu özellikler
    @property
    def report(self) -> dict | None:
        return self._reports.get(self.mode())

    @report.setter
    def report(self, val: dict | None):
        self._reports[self.mode()] = val

    @property
    def tree(self) -> QTreeWidget:
        m = self.mode()
        if m == "pcs":
            return self.pcs_tree
        if m == "ballard":
            return self.tree_bb
        return self.tree_lb

    # ---------------------------------------------------------------- yardımcı kurucular
    def _rx_header_row(self, title: str, box_map: dict[str, QCheckBox], on_change=None) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setContentsMargins(0, 2, 0, 0)
        row.setSpacing(4)
        row.addWidget(look.label(title, "muted"))
        row.addStretch(1)

        def _set_all(val: bool):
            for cb in box_map.values():
                cb.blockSignals(True)
                cb.setChecked(val)
                cb.blockSignals(False)
            if on_change:
                on_change()

        b_all = QToolButton()
        b_all.setText("Tümü")
        b_all.setAutoRaise(True)
        b_all.clicked.connect(lambda: _set_all(True))
        b_none = QToolButton()
        b_none.setText("Temizle")
        b_none.setAutoRaise(True)
        b_none.clicked.connect(lambda: _set_all(False))
        row.addWidget(b_all)
        row.addWidget(b_none)
        return row

    @staticmethod
    def _build_result_tree(headers: list[str]) -> QTreeWidget:
        tw = QTreeWidget()
        tw.setColumnCount(len(headers))
        tw.setHeaderLabels(headers)
        tw.setRootIsDecorated(True)
        tw.setAlternatingRowColors(True)
        h = tw.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Interactive)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        tw.setColumnWidth(1, 340)
        tw.setColumnWidth(5, 34)
        return tw

    @staticmethod
    def _build_test_list(catalog, always) -> QListWidget:
        lst = QListWidget()
        lst.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for tid, title, _fn, per_speed in catalog:
            doc = test_docs.get_test_doc(tid, title)
            it = QListWidgetItem(title + ("  (HS / LS)" if per_speed else ""))
            it.setData(Qt.ItemDataRole.UserRole, tid)
            it.setToolTip(f"{doc.title}\n\n{doc.what}\n\nKontrol: {doc.checks}")
            flags = it.flags() | Qt.ItemFlag.ItemIsUserCheckable
            if tid in always:
                flags &= ~Qt.ItemFlag.ItemIsEnabled
            it.setFlags(flags)
            it.setCheckState(Qt.CheckState.Checked)
            lst.addItem(it)
        return lst

    def _show_test_info(self, tid: str, fallback_title: str = "", fallback_hint: str = "", fail_detail: str = ""):
        doc = test_docs.get_test_doc(tid, fallback_title, fallback_hint)
        dlg = TestInfoDialog(self, doc, fail_detail=fail_detail)
        dlg.exec()

    def _show_selected_list_info(self):
        lst = self._active_list()
        it = lst.currentItem() or (lst.item(0) if lst.count() else None)
        if it is None:
            return
        tid = str(it.data(Qt.ItemDataRole.UserRole) or "")
        self._show_test_info(tid, it.text())

    # ---------------------------------------------------------------- mod & kurulum
    def mode(self) -> str:
        return self.cb_mode.currentData() or "loopback"

    def set_mode(self, mode: str):
        idx = self.cb_mode.findData(mode)
        if idx >= 0:
            self.cb_mode.setCurrentIndex(idx)

    def _set_mode_pill(self, mode: str, text: str, state: str, sub: str = ""):
        self._pill_state[mode] = (text, state, sub)
        if self.mode() == mode:
            self.pill.set(text, state)
            self.lbl_time.setText(sub)

    def _on_mode_changed(self):
        m = self.mode()
        idx = {"loopback": 0, "ballard": 1, "pcs": 2}.get(m, 0)
        self.mode_stack.setCurrentIndex(idx)
        self.list_stack.setCurrentIndex(idx)
        self.result_stack.setCurrentIndex(idx)
        self.common_box.setVisible(m != "pcs")
        self.btn_stop.setVisible(m != "pcs")
        for b in (self.btn_pcs_start, self.btn_pcs_stop, self.btn_pcs_read, self.btn_pcs_clear, self.btn_pcs_inspect):
            b.setVisible(m == "pcs")
        self.btn_run.setText("▶ PCS'ye Yükle & Başlat" if m == "pcs" else "▶ Testi Başlat")
        self.lbl_res_title.setText({
            "loopback": "Loopback Test Sonuçları",
            "ballard": "Ballard Dış Doğrulama Sonuçları",
            "pcs": "Otonom Periyodik PCS Sonuçları",
        }[m])
        self.lbl_note.setText({"loopback": NOTE_LOOPBACK, "ballard": NOTE_BALLARD, "pcs": NOTE_PCS}[m])

        ptxt, pst, psub = self._pill_state[m]
        self.pill.set(ptxt, pst)
        self.lbl_time.setText(psub)
        self.btn_save.setEnabled(self._reports.get(m) is not None)

        if m != "pcs":
            self.stop_pcs_poll()
        else:
            self._update_pcs_size()
            rep = self._reports.get("pcs")
            if rep and rep.get("pcs_busy") and not rep.get("halted_on_fail") and rep.get("run_state") != "TAMAMLANDI":
                self.start_pcs_poll()
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
        cols = 4 if len(rx) <= 8 else 5
        for i, ch in enumerate(rx):
            cb = QCheckBox(f"{ch} ← TX")
            cb.setChecked(ch == "RX0")
            self.rx_grid.addWidget(cb, i // cols, i % cols)
            self._rx_boxes[ch] = cb

            cb2 = QCheckBox(f"{ch} ← BB")
            cb2.setChecked(ch == "RX0")
            self.bb_rx_grid.addWidget(cb2, i // cols, i % cols)
            self._bb_rx_boxes[ch] = cb2

            cb3 = QCheckBox(f"{ch} ← TX")
            cb3.setChecked(ch == "RX0")
            cb3.toggled.connect(self._update_pcs_size)
            self.pcs_rx_grid.addWidget(cb3, i // cols, i % cols)
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

    def selected_pcs_name(self) -> str:
        idx = self.cb_pcs.currentIndex()
        if 0 <= idx < len(self._pcs_list):
            return self._pcs_list[idx].name
        return ""

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
                stop_on_fail=self.chk_pcs_stop_fail.isChecked(),
                imem_aw=self._pcs_imem_aw, dmem_aw=self._pcs_dmem_aw,
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
                stop_on_fail=o["stop_on_fail"],
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
            if self._pcs_started_ts is None:
                self._pcs_started_ts = time.monotonic()
            self._pcs_poll_timer.start()

    def stop_pcs_poll(self):
        self._pcs_poll_timer.stop()

    def _on_pcs_poll_toggled(self, on: bool):
        if not on:
            self.stop_pcs_poll()
        elif self.mode() == "pcs":
            rep = self._reports.get("pcs")
            if rep and rep.get("pcs_busy") and not rep.get("halted_on_fail"):
                self.start_pcs_poll()

    def _on_pcs_poll_tick(self):
        if self.mode() != "pcs" or not self.app.connected or self._busy:
            return
        self.app.do_pcs_read(self.pcs_base_addr(), quiet=True)

    def _pcs_read_now(self):
        self.app.do_pcs_read(self.pcs_base_addr(), quiet=False)
        self.start_pcs_poll()

    def _pcs_start(self):
        if self._pcs_started_ts is None:
            self._pcs_started_ts = time.monotonic()
        self.app.do_pcs_start(self.pcs_base_addr())

    def _pcs_stop(self):
        self.stop_pcs_poll()
        self.app.do_pcs_stop(self.pcs_base_addr())

    def _pcs_apply_gap(self):
        if not self.app.connected or self._busy:
            return
        self.app.do_pcs_update_gap(self.pcs_base_addr(), self.sp_pcs_gap.value())

    def _on_pcs_stop_fail_toggled(self, on: bool):
        self._update_pcs_size()
        rep = self._reports.get("pcs")
        if self.app.connected and not self._busy and rep and rep.get("recognized"):
            self.app.do_pcs_update_stop_on_fail(self.pcs_base_addr(), on)

    def _pcs_inspect_fail(self):
        ch = self._pcs_last_fail_ch or "RX0"
        self.app.do_inspect_pcs_channel(ch)

    # ---------------------------------------------------------------- PCS hat rozetleri & renkli log
    def _clear_pcs_ch_pills(self):
        for p in self._pcs_ch_pills:
            self._pcs_ch_grid.removeWidget(p)
            p.setParent(None)
            p.deleteLater()
        self._pcs_ch_pills.clear()
        self._pcs_ch_wrap.setVisible(False)

    def _update_pcs_ch_pills(self, items: list[tuple[str, str]]):
        if not items:
            self._clear_pcs_ch_pills()
            return
        cols = 6
        if len(self._pcs_ch_pills) != len(items):
            self._clear_pcs_ch_pills()
            for i, (txt, st) in enumerate(items):
                p = look.Pill(txt, st)
                self._pcs_ch_grid.addWidget(p, i // cols, i % cols)
                self._pcs_ch_pills.append(p)
        else:
            for p, (txt, st) in zip(self._pcs_ch_pills, items):
                p.set(txt, st)
        self._pcs_ch_wrap.setVisible(True)

    def _sync_pcs_log_filter_choices(self, chans: list[dict]):
        want = [("", "Tüm Hatlar")] + [(c["name"], c["name"]) for c in chans] + [("TX / Genel", "TX / Genel")]
        cur_data = self.cb_pcs_log_filter.currentData() or ""
        existing = [self.cb_pcs_log_filter.itemData(i) for i in range(self.cb_pcs_log_filter.count())]
        if existing == [w[0] for w in want]:
            return
        self.cb_pcs_log_filter.blockSignals(True)
        self.cb_pcs_log_filter.clear()
        for val, lbl in want:
            self.cb_pcs_log_filter.addItem(lbl, val)
        idx = self.cb_pcs_log_filter.findData(cur_data)
        self.cb_pcs_log_filter.setCurrentIndex(idx if idx >= 0 else 0)
        self.cb_pcs_log_filter.blockSignals(False)

    def _append_colored_log(self, level: str, line: str):
        fmt = QTextCharFormat()
        col_name = {"err": "danger", "warn": "warning", "ok": "success", "info": "accent"}.get(level, "text")
        fmt.setForeground(QBrush(look.color(col_name)))
        if level in ("err", "warn"):
            fmt.setFontWeight(QFont.Weight.DemiBold)
        cur = self.txt_pcs_log.textCursor()
        cur.movePosition(QTextCursor.MoveOperation.End)
        if not self.txt_pcs_log.document().isEmpty():
            cur.insertText("\n")
        cur.insertText(line, fmt)
        self.txt_pcs_log.setTextCursor(cur)
        self.txt_pcs_log.ensureCursorVisible()

    def _rerender_pcs_log(self):
        flt = self.cb_pcs_log_filter.currentData() or ""
        self.txt_pcs_log.clear()
        shown = 0
        for lvl, line in self._pcs_log_entries:
            if not flt or (flt in line):
                self._append_colored_log(lvl, line)
                shown += 1
        total = len(self._pcs_log_entries)
        self.lbl_pcs_log_cnt.setText(f"{shown}/{total} kayıt" if flt else f"{total} kayıt")

    def _clear_pcs_log(self):
        self._pcs_log_entries.clear()
        self.txt_pcs_log.clear()
        self.lbl_pcs_log_cnt.setText("0 kayıt")

    def _save_pcs_log(self):
        if not self._pcs_log_entries:
            return
        d = self.app.rs.out_dir or os.path.expanduser("~")
        p, _ = QFileDialog.getSaveFileName(
            self, "PCS Hata Akışı Logunu Kaydet",
            os.path.join(d, time.strftime("a429_pcs_log_%Y%m%d_%H%M%S.txt")),
            "Metin (*.txt);;Tüm Dosyalar (*)",
        )
        if not p:
            return
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("\n".join(line for _, line in self._pcs_log_entries) + "\n")
        self.app.log(f"[PCS] Hata akışı logu kaydedildi: {p}")

    def _pcs_clear(self):
        self._pcs_prev_telem = None
        self._pcs_started_ts = time.monotonic()
        self._clear_pcs_log()
        self._clear_pcs_ch_pills()
        self.pill_pcs_total.set("Toplam: 0", "")
        self.pill_pcs_pass.set("Hatasız: 0", "")
        self.pill_pcs_fail.set("Hatalı: 0", "")
        self.pill_pcs_rate.set("Başarı: —", "")
        self.pill_pcs_streak.set("Seri: 0", "")
        self.pill_pcs_uptime.set("Süre: 00:00", "")
        self.lbl_pcs_fail_summary.setText("Henüz hata kaydedilmedi — tüm turlar temiz.")
        self.btn_pcs_inspect.setEnabled(False)
        self._pcs_last_fail_ch = ""
        self.app.do_pcs_clear(self.pcs_base_addr())

    # ---------------------------------------------------------------- PCS telemetri güncelleme
    def set_pcs_telemetry(self, t: dict | None, error: str = ""):
        if t is None:
            self._set_mode_pill("pcs", "PCS Hata", "err", error)
            return

        prev = self._pcs_prev_telem
        if prev is not None and (
            t["total_rounds"] < prev.get("total_rounds", 0)
            or t["pcs_base"] != prev.get("pcs_base")
        ):
            prev = None
            self._clear_pcs_log()
            self._pcs_started_ts = time.monotonic()

        events = pcs_test.diff_log_events(prev, t)
        if events:
            flt = self.cb_pcs_log_filter.currentData() or ""
            for lvl, line in events:
                self._pcs_log_entries.append((lvl, line))
                if not flt or (flt in line):
                    self._append_colored_log(lvl, line)
            if len(self._pcs_log_entries) > 3000:
                self._pcs_log_entries = self._pcs_log_entries[-3000:]
            total_l = len(self._pcs_log_entries)
            if flt:
                shown = sum(1 for _, ln in self._pcs_log_entries if flt in ln)
                self.lbl_pcs_log_cnt.setText(f"{shown}/{total_l} kayıt")
            else:
                self.lbl_pcs_log_cnt.setText(f"{total_l} kayıt")

        prev_ch_fails = {c["code"]: int(c["fails"]) for c in prev.get("channels", [])} if prev else {}
        self._pcs_prev_telem = t
        self._reports["pcs"] = t
        if self.mode() == "pcs":
            self.btn_save.setEnabled(True)

        # Checkbox'ı donanımdaki stop_on_fail ile senkron tut
        if t.get("recognized") and "stop_on_fail" in t:
            self.chk_pcs_stop_fail.blockSignals(True)
            self.chk_pcs_stop_fail.setChecked(bool(t["stop_on_fail"]))
            self.chk_pcs_stop_fail.blockSignals(False)

        self._sync_pcs_log_filter_choices(t.get("channels", []))

        last_bad = bool(t.get("last_round_failed", any(x.get("last_failed") for x in t["tests"])))
        cur_bad_chans = {
            ch for x in t["tests"] if x.get("last_failed")
            for ch in (x.get("fail_channels") or ())
        }

        if t["pcs_err"]:
            self._set_mode_pill("pcs", f"PCS HATA ({t['pcs_err_text']})", "err")
            self.stop_pcs_poll()
        elif not t["recognized"]:
            self._set_mode_pill("pcs", "A429 PCS Programı Yüklü Değil", "warn")
        elif t.get("halted_on_fail") or t.get("run_state") == "HATA İLE DURDU":
            self._set_mode_pill("pcs", f"HATA İLE DURDU · Tur #{t['total_rounds']}", "warn")
            self.stop_pcs_poll()
        elif t["run_state"] == "TAMAMLANDI":
            ok = t["total_rounds"] > 0 and not last_bad
            self._set_mode_pill(
                "pcs",
                f"TAMAMLANDI {'✓' if ok else '✗'} ({t['total_rounds']} tur, {t['pass_rounds']} hatasız / {t['fail_rounds']} hatalı)",
                "ok" if ok else "err",
            )
            self.stop_pcs_poll()
        elif t["pcs_busy"]:
            if t["total_rounds"] == 0:
                self._set_mode_pill("pcs", "KOŞUYOR · 0 tur", "accent")
            elif not last_bad:
                self._set_mode_pill("pcs", f"KOŞUYOR · {t['total_rounds']} tur · GEÇTİ ✓", "ok")
            else:
                self._set_mode_pill("pcs", f"KOŞUYOR · {t['total_rounds']} tur · SON TUR KALDI ✗", "err")
        else:
            self._set_mode_pill("pcs", f"DURDURULDU · {t['total_rounds']} tur ({t['fail_rounds']} hatalı)", "warn")
            self.stop_pcs_poll()

        # Üst özet rozetleri
        total = int(t["total_rounds"])
        pass_n = int(t["pass_rounds"])
        fail_n = int(t["fail_rounds"])
        rate_str = f"{t.get('pass_rate_pct', 100.0 * pass_n / total if total else 0.0):.1f}%" if total else "—"
        streak = int(t.get("consec_pass", 0))
        self.pill_pcs_total.set(f"Toplam: {total}", "")
        self.pill_pcs_pass.set(f"Hatasız: {pass_n}", "ok" if pass_n else "")
        self.pill_pcs_fail.set(f"Hatalı: {fail_n}", "err" if fail_n else "")
        self.pill_pcs_rate.set(f"Başarı: {rate_str}", "ok" if total and fail_n == 0 else ("warn" if fail_n else ""))
        self.pill_pcs_streak.set(f"Seri: {streak}", "ok" if streak > 0 else "")
        if self._pcs_started_ts is not None:
            self.pill_pcs_uptime.set(f"Süre: {_fmt_duration(time.monotonic() - self._pcs_started_ts)}", "")

        ch_pill_items: list[tuple[str, str]] = []
        for c in t["channels"]:
            ch_now = (c["name"] in cur_bad_chans) or (last_bad and c["fails"] > prev_ch_fails.get(c["code"], 0))
            if total == 0:
                ch_pill_items.append((f"{c['name']}: —", ""))
            elif ch_now:
                ch_pill_items.append((f"{c['name']} ✗ ({c['fails']})", "err"))
            else:
                ch_pill_items.append((f"{c['name']} ✓ ({c['fails']})", "ok"))
        self._update_pcs_ch_pills(ch_pill_items)

        self.lbl_pcs_meta.setText(
            f"Son tur: {t['last_dur_ms']} ms · Gürültü: {t['max_noise_clk']} clk · "
            f"PCS: {t['pcs_state']} (PC={t['pcs_pc']}, {t['imem_cnt']}/{t['imem_size']} komut)"
        )

        if t["max_rounds"] > 0:
            self.prog.setMaximum(t["max_rounds"])
            self.prog.setValue(min(total, t["max_rounds"]))
            self.prog.setFormat(f"%v / %m tur  ·  {pass_n} hatasız, {fail_n} hatalı")
        else:
            self.prog.setMaximum(100)
            self.prog.setValue(100 if total else 0)
            self.prog.setFormat(f"Sürekli  ·  {total} tur ({pass_n} hatasız, {fail_n} hatalı)")

        # 1) Temiz Test Sonuçları tablosu (sadece testler!)
        self.pcs_tree.clear()
        lf = t.get("last_fail")
        ff = t.get("first_fail")
        for x in t["tests"]:
            cur_failed = bool(x["last_failed"])
            had_fails = x["fails"] > 0
            fch = x.get("fail_channels") or []
            hat_txt = ", ".join(fch) or "—"
            cnt_txt = f"{x['fails']} / {total}"
            if total == 0:
                st_txt, col = "BEKLİYOR", look.color("muted")
                detail = "İlk tur bekleniyor"
            elif cur_failed:
                st_txt, col = "KALDI", look.color("danger")
                detail = x["hint"] or "Son turda kaldı"
            else:
                st_txt, col = "GEÇTİ", look.color("success")
                detail = f"Son tur GEÇTİ (geçmişte {x['fails']} hata)" if had_fails else "Temiz · 0 hata"

            it = QTreeWidgetItem([st_txt, x["title"], cnt_txt, hat_txt if had_fails else "—", detail, ""])
            it.setForeground(0, QBrush(col))
            if cur_failed:
                it.setForeground(2, QBrush(look.color("danger")))
                it.setForeground(3, QBrush(look.color("danger")))
            elif had_fails:
                it.setForeground(2, QBrush(look.color("warning")))
                it.setForeground(3, QBrush(look.color("warning")))
            fnt = it.font(0)
            fnt.setBold(True)
            it.setFont(0, fnt)
            self.pcs_tree.addTopLevelItem(it)

            fail_det = ""
            if lf and lf.get("test_id") == x["tid"]:
                fail_det = pcs_test._fmt_fail_rec(lf)
            elif ff and ff.get("test_id") == x["tid"]:
                fail_det = pcs_test._fmt_fail_rec(ff)
            elif had_fails:
                fail_det = f"Hatalı tur: {x['fails']}/{total} · Hat: {hat_txt}"
            self.pcs_tree.setItemWidget(
                it, 5,
                _info_btn(lambda _c=False, tid=x["tid"], ttl=x["title"], hnt=x["hint"], fd=fail_det:
                          self._show_test_info(tid, ttl, hnt, fd)),
            )

        # 2) Hat / Kanal Durumu tablosu (1..17 kanal destekli)
        self.pcs_ch_tree.clear()
        for c in t["channels"]:
            ch_now = (c["name"] in cur_bad_chans) or (last_bad and c["fails"] > prev_ch_fails.get(c["code"], 0))
            if total == 0:
                c_mark, c_col, c_det = "—", look.color("muted"), "Bekliyor"
            elif ch_now:
                c_mark, c_col, c_det = "KALDI", look.color("danger"), "Son turda hata!"
            elif c["fails"] > 0:
                c_mark, c_col, c_det = "GEÇTİ", look.color("success"), f"Son tur temiz (geçmişte {c['fails']} hata)"
            else:
                c_mark, c_col, c_det = "GEÇTİ", look.color("success"), "Temiz"
            cit = QTreeWidgetItem([c_mark, c["name"], str(c["fails"]), c_det])
            cit.setForeground(0, QBrush(c_col))
            if ch_now:
                cit.setForeground(2, QBrush(look.color("danger")))
            elif c["fails"] > 0:
                cit.setForeground(2, QBrush(look.color("warning")))
            cf = cit.font(0)
            cf.setBold(True)
            cit.setFont(0, cf)
            self.pcs_ch_tree.addTopLevelItem(cit)

        # 3) İlk / Son Hata özeti ve 'Okunan Veriler'de İncele' hedef kanalı
        sum_lines: list[str] = []
        if t["pcs_err"]:
            sum_lines.append(
                f"PCS DONANIM HATASI: {t['pcs_err_text']} "
                f"(PC={t['pcs_pc']}, CODE={t['pcs_err_code']}, ADDR=0x{t['pcs_err_addr']:08X})"
            )
        if ff:
            sum_lines.append(f"İLK HATA: {pcs_test._fmt_fail_rec(ff)}")
        if lf and lf != ff:
            sum_lines.append(f"SON HATA: {pcs_test._fmt_fail_rec(lf)}")
        if t.get("halted_on_fail"):
            sum_lines.append("DURUM: İlk hatada durduruldu — RX Word/Error/BitDiag RAM verileri inceleme için korunuyor.")
        self.lbl_pcs_fail_summary.setText("\n".join(sum_lines) if sum_lines else "Henüz hata kaydedilmedi — tüm turlar temiz.")

        # İnceleme kanalını seç (son hata -> ilk hata -> en çok hata alan kanal)
        target_ch = ""
        for rec in (lf, ff):
            if rec:
                code = int(rec.get("channel_code", 255))
                if 0 <= code < 16:
                    target_ch = f"RX{code}"
                    break
                if code == 16:
                    target_ch = "TB"
                    break
        if not target_ch:
            bad_chs = [c for c in t["channels"] if c["fails"] > 0]
            if bad_chs:
                code = int(bad_chs[0]["code"])
                target_ch = "TB" if code == 16 else f"RX{code}"
        self._pcs_last_fail_ch = target_ch
        self.btn_pcs_inspect.setEnabled(bool(target_ch) and self.app.connected and not self._busy)
        if target_ch:
            self.btn_pcs_inspect.setToolTip(
                f"Hata kaydedilen {channel_label(target_ch)} kanalını seçip Okunan Veriler sekmesinde hemen okur"
            )

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
                "pcs_name": self.selected_pcs_name(),
                "imem_aw": self._pcs_imem_aw,
                "dmem_aw": self._pcs_dmem_aw,
                "rx": [c for c, cb in self._pcs_rx_boxes.items() if cb.isChecked()],
                "tb": self.chk_pcs_tb.isChecked(),
                "selected": sel,
                "gap_ms": self.sp_pcs_gap.value(),
                "max_rounds": self.sp_pcs_max.value(),
                "stop_on_fail": self.chk_pcs_stop_fail.isChecked(),
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
        self.btn_pcs_start.setEnabled(pcs_ok)
        self.btn_pcs_read.setEnabled(pcs_ok)
        self.btn_pcs_stop.setEnabled(pcs_ok)
        self.btn_pcs_clear.setEnabled(pcs_ok)
        self.btn_pcs_gap_apply.setEnabled(pcs_ok)
        self.btn_pcs_inspect.setEnabled(pcs_ok and bool(self._pcs_last_fail_ch))

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
            self.pcs_tree.clear()
            self.pcs_ch_tree.clear()
            self._reports["pcs"] = None
            self._pcs_prev_telem = None
            self._pcs_started_ts = time.monotonic()
            self._pcs_last_fail_ch = ""
            self._clear_pcs_log()
            self._clear_pcs_ch_pills()
            self.pill_pcs_total.set("Toplam: 0", "")
            self.pill_pcs_pass.set("Hatasız: 0", "")
            self.pill_pcs_fail.set("Hatalı: 0", "")
            self.pill_pcs_rate.set("Başarı: —", "")
            self.pill_pcs_streak.set("Seri: 0", "")
            self.pill_pcs_uptime.set("Süre: 00:00", "")
            self.lbl_pcs_meta.setText("")
            self.lbl_pcs_fail_summary.setText("PCS yükleniyor…")
            self.btn_pcs_inspect.setEnabled(False)
            self.btn_save.setEnabled(False)
            self._set_mode_pill("pcs", "PCS'ye yükleniyor…", "accent", "")
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
            self.tree_bb.clear()
            self.pill_bb_pass.set("Geçen: 0", "")
            self.pill_bb_fail.set("Kalan: 0", "")
            self.pill_bb_tx.set("Kart TX → BB RX: Koşuyor…" if o["test_tx"] else "Kart TX → BB RX: Kapalı", "accent" if o["test_tx"] else "")
            self.pill_bb_rx.set("BB TX → Kart RX: Koşuyor…" if o["test_rx"] else "BB TX → Kart RX: Kapalı", "accent" if o["test_rx"] else "")
            self.lbl_bb_meta.setText(f"Kart RX: {', '.join(o['rx']) or '—'} · Hız: {'/'.join(o['speeds'])}")
        else:
            if not o["rx"] and not o["tb"]:
                look.confirm(self, "Loopback Testi", "En az bir RX kanalı ya da TX BIT seçin.", "Tamam", "Kapat")
                return
            self.tree_lb.clear()
            self.pill_lb_pass.set("Geçen: 0", "")
            self.pill_lb_fail.set("Kalan: 0", "")
            self.pill_lb_skip.set("Atlanan: 0", "")
            chs = list(o["rx"]) + (["TX BIT"] if o["tb"] else [])
            self.lbl_lb_meta.setText(f"Kanallar: {', '.join(chs)} · Hız: {'/'.join(o['speeds'])}")

        rmode = o["mode"]
        self._active_run_mode = rmode
        self._reports[rmode] = None
        self.btn_save.setEnabled(False)
        self._set_mode_pill(rmode, "Koşuyor…", "accent", "")
        self.prog.setValue(0)
        self.app.do_run_selftest(o)

    def on_progress(self, done: int, total: int, msg: str):
        self.prog.setMaximum(max(1, total))
        self.prog.setValue(min(done, max(1, total)))
        self.prog.setFormat(f"%p%  ·  {msg}")

    def add_result(self, r: selftest.TestResult):
        target_mode = self._active_run_mode or self.mode()
        tw = self.tree_bb if target_mode == "ballard" else self.tree_lb
        text, role = STATUS_STYLE.get(r.status, (r.status, ""))
        top = QTreeWidgetItem([text, r.title, r.speed or "—", f"{r.duration_s:.2f} s", r.summary, ""])
        col = look.color(role) if role in ("success", "danger") else look.color("muted")
        top.setForeground(0, QBrush(col))
        f = top.font(0)
        f.setBold(True)
        top.setFont(0, f)
        fail_lines = []
        for ck in r.checks:
            mark = {True: "✓", False: "✗", None: "·"}[ck.ok]
            it = QTreeWidgetItem([mark, ck.name, "", "", ck.detail, ""])
            it.setToolTip(1, ck.name)
            it.setToolTip(4, ck.detail)
            if ck.ok is False:
                it.setForeground(0, QBrush(look.color("danger")))
                it.setForeground(1, QBrush(look.color("danger")))
                fail_lines.append(f"{ck.name}: {ck.detail}" if ck.detail else ck.name)
            elif ck.ok:
                it.setForeground(0, QBrush(look.color("success")))
            top.addChild(it)
        for n in r.notes:
            top.addChild(QTreeWidgetItem(["!", n, "", "", "", ""]))
            if r.status in ("FAIL", "ERROR"):
                fail_lines.append(n)
        if r.measurements:
            m = QTreeWidgetItem(["", "Ölçümler", "", "", json.dumps(r.measurements, ensure_ascii=False), ""])
            m.setToolTip(4, json.dumps(r.measurements, ensure_ascii=False, indent=1))
            top.addChild(m)
        tw.addTopLevelItem(top)
        fail_det = " | ".join(fail_lines[:3])
        tw.setItemWidget(
            top, 5,
            _info_btn(lambda _c=False, tid=r.tid, ttl=r.title, fd=fail_det: self._show_test_info(tid, ttl, "", fd)),
        )
        top.setExpanded(r.status != "PASS")
        tw.scrollToItem(top)

    def set_report(self, rep: dict | None, error: str = ""):
        rmode = (rep.get("mode") if rep else None) or self._active_run_mode or self.mode()
        if rmode not in ("loopback", "ballard"):
            rmode = "loopback"
        self._active_run_mode = None
        if rep is None:
            self._set_mode_pill(rmode, "Hata" if error else "Durduruldu", "err" if error else "warn", error)
            return
        self._reports[rmode] = rep
        c = rep["counts"]
        sim = rep.get("sim", {}).get("cycles")
        sub = f"{rep['duration_s']} s" + (f" · RTL {sim / 5e4:.1f} ms simüle" if sim else "")
        if rep["aborted"]:
            self._set_mode_pill(rmode, "Durduruldu", "warn", sub)
        elif rep["passed"]:
            self._set_mode_pill(rmode, f"GEÇTİ ✓  ({c['PASS']} test)", "ok", sub)
        else:
            self._set_mode_pill(rmode, f"KALDI ✗  ({c['FAIL'] + c['ERROR']} başarısız / {len(rep['results'])})", "err", sub)

        n_fail = c["FAIL"] + c["ERROR"]
        if rmode == "ballard":
            self.pill_bb_pass.set(f"Geçen: {c['PASS']}", "ok" if c["PASS"] else "")
            self.pill_bb_fail.set(f"Kalan: {n_fail}", "err" if n_fail else "")
            tx_res = [r for r in rep["results"] if r.tid.startswith("tx_") or r.tid == "duplex"]
            rx_res = [r for r in rep["results"] if r.tid.startswith("rx_") or r.tid == "duplex"]
            if tx_res:
                tx_ok = all(r.status == "PASS" for r in tx_res)
                self.pill_bb_tx.set("Kart TX → BB RX: " + ("GEÇTİ ✓" if tx_ok else "KALDI ✗"), "ok" if tx_ok else "err")
            if rx_res:
                rx_ok = all(r.status == "PASS" for r in rx_res)
                self.pill_bb_rx.set("BB TX → Kart RX: " + ("GEÇTİ ✓" if rx_ok else "KALDI ✗"), "ok" if rx_ok else "err")
        else:
            self.pill_lb_pass.set(f"Geçen: {c['PASS']}", "ok" if c["PASS"] else "")
            self.pill_lb_fail.set(f"Kalan: {n_fail}", "err" if n_fail else "")
            self.pill_lb_skip.set(f"Atlanan: {c['SKIP']}", "")

        if self.mode() == rmode:
            self.btn_save.setEnabled(True)
        self.prog.setFormat("%p%")

    def _save(self):
        rep = self.report
        if not rep:
            return
        d = self.app.rs.out_dir or os.path.expanduser("~")
        rmode = rep.get("mode", self.mode())
        prefix = {"ballard": "a429_ballard_test_", "pcs": "a429_pcs_test_"}.get(rmode, "a429_loopback_test_")
        name = os.path.join(d, time.strftime(prefix + "%Y%m%d_%H%M%S.html"))
        p, flt = QFileDialog.getSaveFileName(
            self, "Test raporunu kaydet", name,
            "HTML Rapor (*.html);;Metin (*.txt);;JSON (*.json)",
        )
        if not p:
            return
        if p.endswith(".json") or "JSON" in flt:
            text = pcs_test.report_json(rep) if rmode == "pcs" else selftest.report_json(rep)
        elif p.endswith(".txt") or "Metin" in flt:
            text = (
                pcs_test.report_text(rep) if rmode == "pcs"
                else (busbox_test.report_text(rep) if rmode == "ballard" else selftest.report_text(rep))
            )
        else:
            rep_for_html = dict(rep)
            rep_for_html.setdefault("mode", rmode)
            text = test_docs.build_html_report(
                rep_for_html,
                log_entries=self._pcs_log_entries if rmode == "pcs" else None,
            )
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.app.log(f"[Test] Rapor kaydedildi: {p}")


def _label(ch: str) -> str:
    return channel_label(ch)
