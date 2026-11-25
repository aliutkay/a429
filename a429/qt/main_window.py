"""ARINC 429 Test Aracı – Qt ana penceresi (AXIL Studio IP arayüzü + çevrimdışı mod)."""
from __future__ import annotations

import copy
import datetime
import os
import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QMenu,
    QMessageBox, QPlainTextEdit, QProgressBar, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from .. import project as P
from ..decode import DecodeSettings, export_txt, import_txt
from ..ip import (
    DEFAULT_OUT_DIR, ReadSettings, native_dir, read_channel, send_rx_config,
    send_tx_config, soft_reset, tx_write as ip_tx_write,
)
from ..model import ConfigInputs, compute
from ..regs import RegMap, channel_label, channel_prefix
from ..txcfg import compute_tx
from . import look
from .config_tab import ConfigTab
from .dialogs import (
    APP, ArincProfilesDialog, FpgaStandardsDialog, GlitchDialog, IcProfileDialog, ReadSettingsDialog,
)
from .figpanel import ChartWindow
from .read_tab import ReadTab
from .tx_sent_tab import TxSentTab
from .txwindow import TxLiveWindow
from .worker import Worker


class MainWindow(QWidget):
    _ev_sig = Signal(dict)        # AXIL Studio olayı (okuyucu thread -> GUI)
    _log_sig = Signal(str)
    _prog_sig = Signal(int, int, str)

    def __init__(self, client=None):
        super().__init__()
        self.client = client
        self.rm = RegMap(client.ip if client else None)
        self.setObjectName("Page")
        self.resize(1460, 880)
        self.setMinimumSize(1060, 680)

        self.bus = Worker(self)
        self.ci = ConfigInputs()
        self.rs = ReadSettings(out_dir=DEFAULT_OUT_DIR)
        self.ds = DecodeSettings()
        self.sessions: list[dict] = []
        self.cur_session: dict | None = None
        self.project_path: str | None = None
        self.dirty = False
        self.res = None
        self.res_tx = None
        self.busy = False
        self._closing = False
        self._stop_flag = threading.Event()
        self.tx_override = "Kapalı"
        self.tx_sched_on = False
        self._write_log: list[str] = []
        self._write_log_path: str | None = None

        self._dialogs: dict[str, QWidget] = {}
        self._charts: dict[tuple[str, str], ChartWindow] = {}
        self._tx_win: TxLiveWindow | None = None

        self._recalc_timer = QTimer(self)
        self._recalc_timer.setSingleShot(True)
        self._recalc_timer.setInterval(250)
        self._recalc_timer.timeout.connect(self.recalc)

        self._save_settings_timer = QTimer(self)
        self._save_settings_timer.setSingleShot(True)
        self._save_settings_timer.setInterval(1000)
        self._save_settings_timer.timeout.connect(self._push_studio_settings)

        # Studio projesinden kayıtlı ayarlar varsa yükle
        if client and isinstance(client.settings.get("a429"), dict):
            try:
                saved = client.settings["a429"]
                self.ci, self.rs, self.ds = P.settings_from(saved)
                self.rs.out_dir = native_dir(self.rs.out_dir)
            except Exception:
                pass

        self._build_ui()
        self._connect_signals()

        self.config_tab.load_from_model()
        self.read_tab.load_settings()
        self._populate_channels()
        if client and isinstance(client.settings.get("a429"), dict):
            ch = client.settings["a429"].get("channel")
            if ch:
                idx = self.cb_channel.findData(ch)
                if idx >= 0:
                    self.cb_channel.setCurrentIndex(idx)
        self.recalc()
        self._update_header()
        self._update_controls()

        QShortcut(QKeySequence.StandardKey.Save, self, self.save_project)
        QShortcut(QKeySequence.StandardKey.Open, self, self.open_project)

    # ================================================================ UI kurulumu
    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 10, 12, 10)
        outer.setSpacing(8)

        # ---- Başlık kartı
        head = look.Card(margins=10, spacing=6)
        hrow = QHBoxLayout()
        hrow.setSpacing(8)

        # Dosya menüsü
        self.btn_file = QToolButton()
        self.btn_file.setText("Dosya ▾")
        self.btn_file.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(self)
        self._add_act(menu, "Yeni proje", self.new_project)
        self._add_act(menu, "Proje aç… (.a429proj)", self.open_project)
        self._add_act(menu, "Proje kaydet", self.save_project)
        self._add_act(menu, "Projeyi farklı kaydet…", lambda: self.save_project(True))
        menu.addSeparator()
        self._add_act(menu, "Config dosyası aç… (.a429cfg)", self.open_cfg)
        self._add_act(menu, "Config dosyasını kaydet… (.a429cfg)", self.save_cfg)
        menu.addSeparator()
        self._add_act(menu, "RX okuma dosyası aç… (.a429read)", self.open_read)
        self._add_act(menu, "Seçili RX okumasını kaydet… (.a429read)", self.save_read)
        self._add_act(menu, "TTL/Excel txt dosyalarından içe aktar…", self.import_ttl)
        self._add_act(menu, "Seçili RX okumasını TTL/Excel txt olarak dışa aktar…", self.export_ttl)
        menu.addSeparator()
        self._add_act(menu, "Hakkında", self._about)
        menu.addSeparator()
        self._add_act(menu, "Çıkış", self.close)
        self.btn_file.setMenu(menu)
        hrow.addWidget(self.btn_file)

        hrow.addWidget(look.label("ARINC 429", "title"))
        self.lbl_ip = look.label("", "muted")
        hrow.addWidget(self.lbl_ip)
        hrow.addSpacing(10)

        hrow.addWidget(look.label("Kanal:", "muted"))
        self.cb_channel = QComboBox()
        self.cb_channel.setMinimumWidth(90)
        self.cb_channel.currentIndexChanged.connect(self._on_channel_changed)
        hrow.addWidget(self.cb_channel)

        hrow.addSpacing(10)
        self.conn_pill = look.Pill("")
        hrow.addWidget(self.conn_pill)

        hrow.addStretch(1)
        self.btn_show_bridge = look.button(
            "Debug Bridge'de göster", None, self._show_in_bridge,
            "AXIL Studio Debug Bridge penceresinde bu IP'yi öne getirir",
        )
        hrow.addWidget(self.btn_show_bridge)
        head.lay.addLayout(hrow)
        outer.addWidget(head)

        # ---- Sekmeler (Config, RX Okunan Veriler, TX Gönderilen Veriler)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        tab_card = look.Card(margins=0, spacing=0)
        tab_card.lay.addWidget(self.tabs)
        outer.addWidget(tab_card, 1)

        self.config_tab = ConfigTab(self)
        self.read_tab = ReadTab(self)
        self.tx_sent_tab = TxSentTab(self)
        self.tabs.addTab(self.config_tab, "Config")
        self.tabs.addTab(self.read_tab, "RX Okunan Veriler")
        self.tabs.addTab(self.tx_sent_tab, "TX Gönderilen Veriler")

        # ---- Alt işlem çubuğu + katlanabilir log
        foot = look.Card(margins=8, spacing=6)
        brow = QHBoxLayout()
        brow.setSpacing(6)
        self.btn_send_rx = look.button("RX Config gönder", "primary", self.do_send_rx_cfg)
        self.btn_read_rx = look.button("RX verilerini oku", "primary", self.do_read)
        self.btn_all = look.button("Config + oku", None, self.do_all)
        self.btn_read_opts = look.button("Okuma ayarları…", None, self.open_read_settings)
        self.btn_send_tx = look.button("TX Config gönder", None, self.do_send_tx_cfg)
        self.btn_tx_live = look.button("TX Canlı Kontrol…", None, self.open_tx_live)
        self.btn_reset = look.button("IP reset", "danger", self.do_ip_reset)
        self.btn_stop = look.button("Durdur", None, self.do_stop)
        self.btn_log_toggle = look.button("Log ▾", None, self._toggle_log)

        for b in (
            self.btn_send_rx, self.btn_read_rx, self.btn_all, self.btn_read_opts,
            self.btn_send_tx, self.btn_tx_live, self.btn_reset, self.btn_stop,
        ):
            brow.addWidget(b)
        brow.addStretch(1)
        brow.addWidget(self.btn_log_toggle)
        foot.lay.addLayout(brow)

        self.prog = QProgressBar()
        self.prog.setRange(0, 100)
        self.prog.setValue(0)
        self.prog.setVisible(False)
        foot.lay.addWidget(self.prog)

        self.log_box = QWidget()
        llay = QVBoxLayout(self.log_box)
        llay.setContentsMargins(0, 0, 0, 0)
        llay.setSpacing(4)
        self.log_txt = QPlainTextEdit()
        self.log_txt.setReadOnly(True)
        self.log_txt.setFont(look.mono_font(-1))
        self.log_txt.setMaximumBlockCount(4000)
        self.log_txt.setFixedHeight(130)
        llay.addWidget(self.log_txt)
        lbar = QHBoxLayout()
        lbar.addWidget(look.button("Logu temizle", None, self.log_txt.clear))
        lbar.addWidget(look.button("Logu kaydet…", None, self._save_log))
        lbar.addStretch(1)
        llay.addLayout(lbar)
        self.log_box.setVisible(False)
        foot.lay.addWidget(self.log_box)
        outer.addWidget(foot)

        # Durum satırı
        self.lbl_status = look.label("Hazır.", "muted")
        outer.addWidget(self.lbl_status)

    @staticmethod
    def _add_act(menu: QMenu, text: str, slot):
        act = QAction(text, menu)
        act.triggered.connect(slot)
        menu.addAction(act)

    def _connect_signals(self):
        self._ev_sig.connect(self._on_studio_event, Qt.ConnectionType.QueuedConnection)
        self._log_sig.connect(self._append_log, Qt.ConnectionType.QueuedConnection)
        self._prog_sig.connect(self._on_progress, Qt.ConnectionType.QueuedConnection)
        if self.client is not None:
            self.client.on_event = self._ev_sig.emit

    # ================================================================ AXIL Studio olayları
    @property
    def connected(self) -> bool:
        return bool(self.client and self.client.connected)

    def current_channel(self) -> str:
        return self.cb_channel.currentData() or "RX0"

    def _populate_channels(self):
        cur = self.current_channel()
        self.cb_channel.blockSignals(True)
        self.cb_channel.clear()
        for ch in self.rm.channels():
            self.cb_channel.addItem(channel_label(ch), ch)
        idx = self.cb_channel.findData(cur)
        if idx >= 0:
            self.cb_channel.setCurrentIndex(idx)
        self.cb_channel.blockSignals(False)

    def _on_channel_changed(self):
        self.recalc()
        self._update_controls()
        self._schedule_studio_settings()

    def _on_studio_event(self, ev: dict):
        kind = ev.get("event")
        if kind == "connection":
            self._update_header()
            self._update_controls()
        elif kind == "ip":
            self.rm = RegMap(self.client.ip if self.client else None)
            self._populate_channels()
            self.recalc()
            self._update_header()
            self._update_controls()
        elif kind == "ip_removed":
            QMessageBox.warning(self, APP, f"{self.rm.name} artık adres haritasında değil.")
            self._closing = True
            self.close()
        elif kind == "theme":
            look.apply(QApplication.instance(), ev.get("theme"))
            self.recalc()
            self.read_tab.refresh()
        elif kind == "raise":
            self.showNormal()
            self.raise_()
            self.activateWindow()
        elif kind == "closing":
            self._stop_flag.set()
            self._closing = True
            self.close()

    def _update_header(self):
        name = os.path.basename(self.project_path) if self.project_path else "Yeni proje"
        star = " *" if self.dirty else ""
        if self.client is None:
            self.lbl_ip.setText("Çevrimdışı mod")
            self.conn_pill.set("● Çevrimdışı", "warn")
            self.setWindowTitle(f"{APP} – {name}{star}")
        else:
            self.lbl_ip.setText(f"{self.rm.name} · 0x{self.rm.base:08X}")
            if self.connected:
                self.conn_pill.set("● Debug Bridge bağlı", "ok")
            else:
                self.conn_pill.set("● Debug Bridge bağlı değil", "err")
            self.setWindowTitle(f"{self.rm.name} — {APP} – {name}{star}")

    def _update_controls(self):
        ch = self.current_channel()
        conn = self.connected and not self.busy
        rx_cfg_miss = self.rm.missing_for_rx_config(ch) if self.rm.is_loaded() else ["çevrimdışı"]
        rx_rd_miss = self.rm.missing_for_rx_read(ch) if self.rm.is_loaded() else ["çevrimdışı"]
        tx_cfg_miss = self.rm.missing_for_tx_config() if self.rm.is_loaded() else ["çevrimdışı"]
        tx_live_miss = self.rm.missing_for_tx_live() if self.rm.is_loaded() else ["çevrimdışı"]
        rst_miss = self.rm.missing_for_reset() if self.rm.is_loaded() else ["çevrimdışı"]

        def cfg_btn(btn, ok: bool, miss: list[str], default_tip: str):
            btn.setEnabled(conn and ok)
            if not self.client:
                btn.setToolTip("Çevrimdışı modda kapalı (AXIL Studio Debug Bridge'den açın).")
            elif not self.connected:
                btn.setToolTip("Debug Bridge karta bağlı değil.")
            elif miss:
                btn.setToolTip("IP haritasında eksik register'lar:\n" + ", ".join(miss[:8]))
            else:
                btn.setToolTip(default_tip)

        cfg_btn(self.btn_send_rx, not rx_cfg_miss, rx_cfg_miss, f"{channel_label(ch)} kanalına Custom RX Config yazar ve doğrular")
        cfg_btn(self.btn_read_rx, not rx_rd_miss, rx_rd_miss, f"{channel_label(ch)} kanalından Word, Error ve Bit Diagnostic verilerini okur")
        cfg_btn(self.btn_all, not rx_cfg_miss and not rx_rd_miss, rx_cfg_miss + rx_rd_miss, "RX Config gönder + verileri oku")
        cfg_btn(self.btn_send_tx, not tx_cfg_miss, tx_cfg_miss, "TX Config register'larını yazar ve doğrular")
        cfg_btn(self.btn_reset, not rst_miss, rst_miss, "SOFT_RESET.ALL darbesi gönderir")
        self.btn_tx_live.setEnabled(not self.busy)
        if tx_live_miss and self.client:
            self.btn_tx_live.setToolTip("Bazı TX register'ları haritada eksik: " + ", ".join(tx_live_miss[:6]))
        else:
            self.btn_tx_live.setToolTip("TX Canlı Kontrol penceresini açar")
        self.btn_stop.setEnabled(self.busy)
        self.btn_show_bridge.setEnabled(self.client is not None)
        self.config_tab.btn_rx_add_cfg.setEnabled(self.client is not None and not rx_cfg_miss)
        self.config_tab.btn_tx_add_cfg.setEnabled(self.client is not None and not tx_cfg_miss)

    def _show_in_bridge(self):
        if self.client:
            self.bus.run(lambda: self.client.show_register(None))

    def _schedule_studio_settings(self):
        if self.client is not None:
            self._save_settings_timer.start()

    def _push_studio_settings(self):
        if self.client is None:
            return
        payload = P.settings_dict(self.ci, self.rs, self.ds)
        payload["channel"] = self.current_channel()
        self.bus.run(lambda: self.client.set_settings(a429=payload))

    # ================================================================ hesaplama / ayarlar
    def mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self._update_header()
        self._schedule_studio_settings()

    def set_status(self, text: str):
        self.lbl_status.setText(text)

    def log(self, text: str):
        self._log_sig.emit(text)

    def _append_log(self, text: str):
        self.log_txt.appendPlainText(text)

    def _on_progress(self, done: int, total: int, msg: str):
        self.prog.setMaximum(max(1, total))
        self.prog.setValue(min(done, max(1, total)))
        self.set_status(msg)

    def _toggle_log(self):
        vis = not self.log_box.isVisible()
        self.log_box.setVisible(vis)
        self.btn_log_toggle.setText("Log ▴" if vis else "Log ▾")

    def _save_log(self):
        p, _ = QFileDialog.getSaveFileName(self, "Logu kaydet", "", "Metin (*.txt)")
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.log_txt.toPlainText())

    def schedule_recalc(self):
        self.mark_dirty()
        self._recalc_timer.start()

    def recalc(self):
        self._recalc_timer.stop()
        try:
            self.config_tab.read_to_model()
            self.res = compute(self.ci, self.rm, self.current_channel())
        except Exception as e:
            self.set_status(f"Giriş hatası: {e}")
            return
        self.recalc_tx()
        self.config_tab.update_results(self.res, self.res_tx)
        for win in list(self._charts.values()):
            if win.isVisible():
                win.draw()
        self.read_tab.refresh()
        self.set_status("Config hesaplandı.")

    def recalc_tx(self):
        try:
            self.res_tx = compute_tx(self.ci, self.tx_override, self.rm)
        except Exception:
            self.res_tx = None
        if self.res is not None:
            self.config_tab.update_results(self.res, self.res_tx)

    def select_profile(self, key: str, name: str):
        setattr(self.ci, key, name)
        self.config_tab.refresh_combos()
        self.mark_dirty()
        self.recalc()

    def refresh_profiles(self):
        self.config_tab.refresh_combos()
        self.mark_dirty()
        self.recalc()

    def refresh_fpga_combo(self):
        self.config_tab.refresh_combos()

    # ================================================================ diyaloglar
    def _open_dialog(self, key: str, factory):
        dlg = self._dialogs.get(key)
        if dlg is not None and dlg.isVisible():
            dlg.raise_()
            dlg.activateWindow()
            return
        dlg = factory()
        self._dialogs[key] = dlg
        dlg.show()

    def open_arinc_dialog(self):
        self._open_dialog("arinc", lambda: ArincProfilesDialog(self))

    def open_ic_dialog(self):
        self._open_dialog("ic", lambda: IcProfileDialog(self))

    def open_fpga_dialog(self):
        self._open_dialog("fpga", lambda: FpgaStandardsDialog(self))

    def open_glitch_dialog(self):
        self._open_dialog("glitch", lambda: GlitchDialog(self))

    def open_chart(self, kind: str, case: str):
        win = self._charts.get((kind, case))
        if win is not None and win.isVisible():
            win.raise_()
            win.activateWindow()
            return
        win = ChartWindow(self, kind, case)
        self._charts[(kind, case)] = win
        win.show()

    def open_read_settings(self):
        dlg = ReadSettingsDialog(self, self.rs)
        if dlg.exec():
            self.mark_dirty()

    def open_tx_live(self):
        if self._tx_win is not None and self._tx_win.isVisible():
            self._tx_win.raise_()
            self._tx_win.activateWindow()
            return
        self._tx_win = TxLiveWindow(self)
        self._tx_win.show()

    # ================================================================ Debug Bridge config listesi
    def add_rx_to_bridge_config(self):
        if not self.client or not self.res:
            return
        ch = self.current_channel()
        p = channel_prefix(ch)
        rows = [(p + "CFG_SEL", 2)] + [(p + k, v) for k, v in self.res.rx_values.items()] + [(p + "CFG_APPLY", 1)]
        self.bus.run(
            lambda: self.client.add_config(rows),
            ok=lambda _: self.set_status(f"{channel_label(ch)} RX Config Debug Bridge listesine eklendi."),
            err=lambda e: QMessageBox.warning(self, APP, str(e)),
        )

    def add_tx_to_bridge_config(self):
        if not self.client or not self.res_tx:
            return
        rows = list(self.res_tx["writes"])
        self.bus.run(
            lambda: self.client.add_config(rows),
            ok=lambda _: self.set_status("TX Config Debug Bridge listesine eklendi."),
            err=lambda e: QMessageBox.warning(self, APP, str(e)),
        )

    # ================================================================ IP işlemleri (worker)
    def _record_write(self, reg_name: str, offset: int, value: int):
        now = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self._write_log.append(f"{now}\t{reg_name}\t0x{offset:04X}\t0x{value:08X}")

    def _flush_write_log(self):
        lines, self._write_log = self._write_log, []
        if not lines or not self.rs.auto_write_log:
            return
        try:
            out_dir = native_dir(self.rs.out_dir)
            os.makedirs(out_dir, exist_ok=True)
            if self._write_log_path is None:
                name = datetime.datetime.now().strftime("yazma_log_%Y%m%d_%H%M%S.txt")
                self._write_log_path = os.path.join(out_dir, name)
                self.log(f"Yazma logu: {self._write_log_path}")
            with open(self._write_log_path, "a", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except OSError as e:
            self.log(f"Yazma logu yazılamadı: {e}")

    def _run_job(self, title: str, fn, on_ok=None, on_done=None, show_progress: bool = False) -> bool:
        if self.busy or not self.connected:
            return False
        self._stop_flag.clear()
        self.busy = True
        self.prog.setVisible(show_progress)
        self.prog.setValue(0)
        self._update_controls()
        self.set_status(f"{title}…")

        def ok(result):
            self.busy = False
            self.prog.setVisible(False)
            self._flush_write_log()
            self._update_controls()
            self.set_status(f"{title}: tamam.")
            if on_ok:
                on_ok(result)
            if on_done:
                on_done(True)

        def fail(exc):
            self.busy = False
            self.prog.setVisible(False)
            self._flush_write_log()
            self._update_controls()
            self.log(f"HATA ({title}): {exc}")
            self.set_status(f"{title}: başarısız.")
            if on_done:
                on_done(False)
            if getattr(exc, "code", "") != "closed":
                QMessageBox.critical(self, title, str(exc))

        self.bus.run(fn, ok=ok, err=fail)
        return True

    def do_send_rx_cfg(self):
        self.recalc()
        if not self.res:
            return
        ch = self.current_channel()
        vals = dict(self.res.rx_values)
        rm = self.rm

        def job():
            send_rx_config(self.client, rm, ch, vals, verify=True, log=self.log, on_write=self._record_write)
            self.client.log(f"ARINC 429: {ch} RX Config gönderildi ve doğrulandı.")

        self._run_job(f"{channel_label(ch)} RX Config gönderiliyor", job)

    def do_read(self):
        self.recalc()
        if not self.res:
            return
        ch = self.current_channel()
        opts = copy.deepcopy(self.rs)
        rm = self.rm
        mhz = self.ci.clk_mhz

        def job():
            return read_channel(
                self.client, rm, ch, opts,
                progress=lambda d, t, m: self._prog_sig.emit(d, t, m),
                stop_flag=self._stop_flag,
                log=self.log,
                on_write=self._record_write,
            )

        def done(data):
            s = P.new_session(data, self.ci, self.rs, self.ds)
            s["clk_mhz"] = mhz
            self.add_session(s, save_file=True)
            self.tabs.setCurrentIndex(1)

        self._run_job(f"{channel_label(ch)} RX verileri okunuyor", job, on_ok=done, show_progress=True)

    def do_all(self):
        self.recalc()
        if not self.res:
            return
        ch = self.current_channel()
        vals = dict(self.res.rx_values)
        opts = copy.deepcopy(self.rs)
        rm = self.rm
        mhz = self.ci.clk_mhz

        def job():
            send_rx_config(self.client, rm, ch, vals, verify=True, log=self.log, on_write=self._record_write)
            return read_channel(
                self.client, rm, ch, opts,
                progress=lambda d, t, m: self._prog_sig.emit(d, t, m),
                stop_flag=self._stop_flag,
                log=self.log,
                on_write=self._record_write,
            )

        def done(data):
            s = P.new_session(data, self.ci, self.rs, self.ds)
            s["clk_mhz"] = mhz
            self.add_session(s, save_file=True)
            self.tabs.setCurrentIndex(1)

        self._run_job(f"{channel_label(ch)} Config + okuma", job, on_ok=done, show_progress=True)

    def do_send_tx_cfg(self):
        self.recalc()
        if not self.res_tx or self.res_tx["errors"]:
            msg = "\n".join(self.res_tx["errors"][:8]) if self.res_tx else "TX Config hesaplanamadı."
            QMessageBox.warning(self, APP, f"TX Config gönderilemez:\n{msg}")
            return
        writes = list(self.res_tx["writes"])
        rm = self.rm

        def job():
            send_tx_config(self.client, rm, writes, verify=True, log=self.log, on_write=self._record_write)
            self.client.log("ARINC 429: TX Config gönderildi ve doğrulandı.")

        self._run_job("TX Config gönderiliyor", job)

    def tx_write(self, title: str, writes: list[tuple[str, int]], on_done=None, quiet: bool = False, verify: bool = True) -> bool:
        if not self.connected:
            QMessageBox.information(self, APP, "Debug Bridge bağlı değil (çevrimdışı modda yazma yapılamaz).")
            return False
        miss = self.rm.missing([r for r, _ in writes])
        if miss:
            QMessageBox.warning(self, APP, "IP haritasında eksik TX register'ları:\n" + ", ".join(miss))
            return False
        rm = self.rm

        def job():
            ip_tx_write(self.client, rm, writes, verify=verify, quiet=quiet, log=self.log, on_write=self._record_write)

        return self._run_job(title, job, on_done=on_done)

    def do_ip_reset(self):
        if not look.confirm(self, APP, "ARINC 429 IP bloğu resetlensin mi? (SOFT_RESET.ALL darbesi gönderilir)", "Resetle"):
            return
        rm = self.rm
        self._run_job("IP reset", lambda: soft_reset(self.client, rm, "ALL", log=self.log, on_write=self._record_write))

    def do_stop(self):
        self._stop_flag.set()
        self.set_status("Durduruluyor…")

    # ================================================================ oturumlar & dosya
    def add_session(self, s: dict, save_file: bool):
        names = {x["name"] for x in self.sessions}
        base, i = s["name"], 2
        while s["name"] in names:
            s["name"] = f"{base}_{i}"
            i += 1
        if save_file:
            try:
                out_dir = native_dir(self.rs.out_dir)
                os.makedirs(out_dir, exist_ok=True)
                p = os.path.join(out_dir, s["name"] + ".a429read")
                P.save_session(p, s)
                self.log(f"Okuma kaydedildi: {p}")
                if self.rs.auto_txt:
                    d = os.path.join(out_dir, s["name"] + "_txt")
                    os.makedirs(d, exist_ok=True)
                    for fn, txt in export_txt(s).items():
                        with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
                            f.write(txt + "\n")
            except Exception as e:
                self.log(f"Okuma dosyası yazılamadı: {e}")
        self.sessions.append(s)
        self.cur_session = s
        self.mark_dirty()
        self.read_tab.refresh_sessions()

    def rename_session(self):
        if not self.cur_session:
            return
        name, ok = QInputDialog.getText(self, APP, "Okuma adı:", text=self.cur_session["name"])
        name = name.strip()
        if not ok or not name or name == self.cur_session["name"]:
            return
        if any(x is not self.cur_session and x["name"] == name for x in self.sessions):
            QMessageBox.warning(self, APP, f"'{name}' adında bir okuma zaten var.")
            return
        self.cur_session["name"] = name
        self.mark_dirty()
        self.read_tab.refresh_sessions()

    def delete_session(self):
        if not self.cur_session:
            return
        if not look.confirm(self, APP, f"'{self.cur_session['name']}' projeden çıkarılsın mı?", "Çıkar"):
            return
        self.sessions.remove(self.cur_session)
        self.cur_session = self.sessions[-1] if self.sessions else None
        self.mark_dirty()
        self.read_tab.refresh_sessions()

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        ans = QMessageBox.question(
            self, APP, "Kaydedilmemiş değişiklikler var. Projeyi kaydedeyim mi?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
        )
        if ans == QMessageBox.StandardButton.Cancel:
            return False
        if ans == QMessageBox.StandardButton.Yes:
            return self.save_project()
        return True

    def new_project(self):
        if not self._confirm_discard():
            return
        out = self.rs.out_dir
        self.ci, self.rs, self.ds = ConfigInputs(), ReadSettings(out_dir=out), DecodeSettings()
        self.sessions, self.cur_session, self.project_path, self.dirty = [], None, None, False
        self.config_tab.load_from_model()
        self.read_tab.load_settings()
        self.recalc()
        self.read_tab.refresh_sessions()
        self._update_header()

    def open_project(self):
        if not self._confirm_discard():
            return
        p, _ = QFileDialog.getOpenFileName(self, "Proje aç", "", "ARINC429 proje (*.a429proj);;Tümü (*.*)")
        if not p:
            return
        try:
            self.ci, self.rs, self.ds, self.sessions = P.load_project(p)
            self.rs.out_dir = native_dir(self.rs.out_dir)
        except Exception as e:
            QMessageBox.critical(self, APP, f"Proje açılamadı:\n{e}")
            return
        self.project_path, self.dirty = p, False
        self.cur_session = self.sessions[-1] if self.sessions else None
        self.config_tab.load_from_model()
        self.read_tab.load_settings()
        self.recalc()
        self.read_tab.refresh_sessions()
        self._update_header()
        self.set_status(f"Proje açıldı: {p} ({len(self.sessions)} okuma)")

    def save_project(self, ask: bool = False) -> bool:
        try:
            self.config_tab.read_to_model()
            self.read_tab.read_settings()
        except ValueError as e:
            QMessageBox.warning(self, APP, f"Önce alanları düzeltin:\n{e}")
            return False
        p = self.project_path
        if ask or not p:
            p, _ = QFileDialog.getSaveFileName(self, "Projeyi kaydet", p or "", "ARINC429 proje (*.a429proj)")
            if not p:
                return False
            if not p.endswith(".a429proj"):
                p += ".a429proj"
        try:
            P.save_project(p, self.ci, self.rs, self.ds, self.sessions)
        except Exception as e:
            QMessageBox.critical(self, APP, f"Kaydedilemedi:\n{e}")
            return False
        self.project_path, self.dirty = p, False
        self._update_header()
        self.set_status(f"Proje kaydedildi: {p}")
        return True

    def open_cfg(self):
        p, _ = QFileDialog.getOpenFileName(self, "Config dosyası aç", "", "ARINC429 config (*.a429cfg);;Tümü (*.*)")
        if not p:
            return
        try:
            self.ci, rs, self.ds = P.load_config(p)
            self.rs.out_dir = native_dir(rs.out_dir or self.rs.out_dir)
        except Exception as e:
            QMessageBox.critical(self, APP, f"Config açılamadı:\n{e}")
            return
        self.config_tab.load_from_model()
        self.read_tab.load_settings()
        self.recalc()
        self.mark_dirty()
        self.set_status(f"Config yüklendi: {p}")

    def save_cfg(self):
        try:
            self.config_tab.read_to_model()
            self.read_tab.read_settings()
        except ValueError as e:
            QMessageBox.warning(self, APP, str(e))
            return
        p, _ = QFileDialog.getSaveFileName(self, "Config dosyasını kaydet", "", "ARINC429 config (*.a429cfg)")
        if p:
            if not p.endswith(".a429cfg"):
                p += ".a429cfg"
            P.save_config(p, self.ci, self.rs, self.ds)
            self.set_status(f"Config kaydedildi: {p}")

    def open_read(self):
        ps, _ = QFileDialog.getOpenFileNames(self, "RX okuma dosyası aç", "", "ARINC429 okuma (*.a429read);;Tümü (*.*)")
        for p in ps:
            try:
                s = P.load_session(p)
            except Exception as e:
                QMessageBox.critical(self, APP, f"{p} açılamadı:\n{e}")
                continue
            self.add_session(s, save_file=False)

    def save_read(self):
        if not self.cur_session:
            return
        p, _ = QFileDialog.getSaveFileName(
            self, "RX okumasını kaydet", self.cur_session["name"] + ".a429read", "ARINC429 okuma (*.a429read)"
        )
        if p:
            P.save_session(p, self.cur_session)
            self.set_status(f"Okuma kaydedildi: {p}")

    def import_ttl(self):
        d = QFileDialog.getExistingDirectory(self, "a429_words.txt vb. dosyaların olduğu klasör")
        if not d:
            return
        def rd(n):
            fp = os.path.join(d, n)
            return open(fp, encoding="utf-8", errors="ignore").read() if os.path.exists(fp) else ""
        s = import_txt(rd("a429_words.txt"), rd("a429_errors.txt"), rd("a429_bits.txt"), rd("a429_summary.txt"))
        s = P.new_session(s, self.ci, self.rs, self.ds, name="ttl_" + os.path.basename(d.rstrip("/\\")))
        self.add_session(s, save_file=False)

    def export_ttl(self):
        if not self.cur_session:
            return
        d = QFileDialog.getExistingDirectory(self, "Dışa aktarılacak klasör")
        if not d:
            return
        for fn, txt in export_txt(self.cur_session).items():
            with open(os.path.join(d, fn), "w", encoding="utf-8") as f:
                f.write(txt + "\n")
        self.set_status(f"TTL/Excel txt dosyaları yazıldı: {d}")

    def _about(self):
        QMessageBox.information(
            self, APP,
            "ARINC 429 Test Aracı (AXIL Studio IP arayüzü · PySide6)\n\n"
            "• Config hesabı, RX okuma ve çözümleme, dalga formu grafikleri, TX canlı kontrol.\n"
            "• Donanım erişimi AXIL Studio UART-to-AXI Debug Bridge üzerinden yapılır.\n"
            "• AXIL Studio olmadan çevrimdışı modda açılabilir (--sim ile simülatör).",
        )

    def closeEvent(self, ev):
        if not self._closing:
            if self.busy and not look.confirm(self, APP, "İşlem sürüyor. Durdurulup çıkılsın mı?", "Durdur ve çık"):
                ev.ignore()
                return
            if not self._confirm_discard():
                ev.ignore()
                return
        self._stop_flag.set()
        if self._tx_win is not None:
            self._tx_win.close()
        if self.client is not None:
            self.client.on_event = lambda _: None
        super().closeEvent(ev)
