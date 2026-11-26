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
    QMessageBox, QTabWidget, QToolButton, QVBoxLayout, QWidget,
)

from .. import project as P
from ..decode import DecodeSettings, export_txt, import_txt
from ..ip import (
    DEFAULT_OUT_DIR, ReadSettings, clear_channel, clear_tx_checker_fifo, native_dir,
    read_channel, read_channel_status, read_rx_active_config, read_tx_active_config,
    read_tx_bit_status, recompare_active_config, send_rx_config, send_tx_config,
    set_channel_enable, set_tx_checker, soft_reset, tx_write as ip_tx_write, check_ip, apply_fix, bridge_rows,
)
from ..model import ConfigInputs, compute
from ..regs import RegMap, channel_label, channel_prefix
from ..txcfg import compute_tx
from . import look
from .config_tab import ConfigTab
from .control_tab import ControlTab
from .dialogs import (
    APP, ActiveConfigDialog, ArincProfilesDialog, FpgaStandardsDialog, GlitchDialog,
    IcProfileDialog, IpHealthDialog, TxDriverDialog, TxFpgaDialog,
)
from .figpanel import ChartWindow
from .read_tab import ReadTab
from .tx_sent_tab import TxSentTab
from .test_tab import TestTab
from .worker import Worker


class MainWindow(QWidget):
    _ev_sig = Signal(dict)        # AXIL Studio olayı (okuyucu thread -> GUI)
    _log_sig = Signal(str)
    _prog_sig = Signal(int, int, str)
    _test_sig = Signal(object)    # selftest.TestResult (worker -> GUI)

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
        self.tx_history: list[dict] = []
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
        self._last_rx_act: dict | None = None
        self._last_tx_act: dict | None = None
        self._last_health: dict | None = None

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
        self.control_tab.load_from_model()
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
        if self.connected:
            QTimer.singleShot(50, self.do_refresh_status)
            QTimer.singleShot(120, self.do_refresh_tx_bit)
            QTimer.singleShot(160, self.do_check_tx_config)
            QTimer.singleShot(220, self.do_check_ip)

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
        self.btn_file.setText("Dosya")
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

        # ---- Sekmeler (Config, Kontrol, RX Okunan Veriler, TX Gönderilen Veriler)
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        outer.addWidget(look.wrap_tabs(self.tabs, "Card"), 1)

        self.config_tab = ConfigTab(self)
        self.control_tab = ControlTab(self)
        self.read_tab = ReadTab(self)
        self.tx_sent_tab = TxSentTab(self)
        self.test_tab = TestTab(self)
        self.tabs.addTab(self.config_tab, "Config")
        self.tabs.addTab(self.control_tab, "Kontrol")
        self.tabs.addTab(self.read_tab, "RX Okunan Veriler")
        self.tabs.addTab(self.tx_sent_tab, "TX Gönderilen Veriler")
        self.tabs.addTab(self.test_tab, "Test")

        # Kontrol sekmesindeki bileşenlere kısa referanslar
        self.btn_send_rx = self.control_tab.btn_send_rx
        self.btn_read_rx = self.control_tab.btn_read_rx
        self.btn_send_tx = self.control_tab.btn_send_tx
        self.btn_tx_live = self.control_tab.btn_tx_live
        self.btn_reset = self.control_tab.btn_reset
        self.btn_stop = self.control_tab.btn_stop
        self.prog = self.control_tab.prog
        self.log_txt = self.control_tab.log_txt

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
        self._test_sig.connect(self.test_tab.add_result, Qt.ConnectionType.QueuedConnection)
        if self.client is not None:
            self.client.on_event = self._ev_sig.emit

    # ================================================================ AXIL Studio olayları
    @property
    def connected(self) -> bool:
        return bool(self.client and self.client.connected)

    def current_channel(self) -> str:
        return self.cb_channel.currentData() or "RX0"

    def _populate_channels(self):
        self.test_tab.populate_channels(self.rm)
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
        self._last_rx_act = None
        self.control_tab.update_rx_active_config(None)
        self.recalc()
        self._update_controls()
        self._schedule_studio_settings()
        if self.connected and not self.busy:
            self.do_refresh_status()

    def _on_studio_event(self, ev: dict):
        kind = ev.get("event")
        if kind == "connection":
            self._update_header()
            self._update_controls()
            if self.connected:
                QTimer.singleShot(50, self.do_refresh_status)
                QTimer.singleShot(120, self.do_check_tx_config)
                QTimer.singleShot(200, self.do_check_ip)
            else:
                self._last_rx_act = None
                self._last_tx_act = None
                self.control_tab.update_rx_active_config(None)
                self.control_tab.update_tx_active_config(None)
        elif kind == "ip":
            self.rm = RegMap(self.client.ip if self.client else None)
            self._last_rx_act = None
            self._last_tx_act = None
            self._populate_channels()
            self.recalc()
            self._update_header()
            self._update_controls()
            self._last_health = None
            self.control_tab.update_health(None)
            if self.connected:
                QTimer.singleShot(50, self.do_refresh_status)
                QTimer.singleShot(120, self.do_check_tx_config)
                QTimer.singleShot(200, self.do_check_ip)
        elif kind == "ip_removed":
            QMessageBox.warning(self, APP, f"{self.rm.name} artık adres haritasında değil.")
            self._closing = True
            self.close()
        elif kind == "theme":
            look.apply(QApplication.instance(), ev.get("theme"))
            self.config_tab.restyle_icons()
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
        cfg_btn(self.btn_send_tx, not tx_cfg_miss, tx_cfg_miss, "TX Config register'larını yazar ve doğrular")
        cfg_btn(self.btn_reset, not rst_miss, rst_miss, "SOFT_RESET.ALL darbesi gönderir")
        cfg_btn(self.control_tab.btn_health, self.rm.is_loaded(), [],
                "Logger enable/freeze, hat (LINE/SYNC_WAIT), IP sürümü, saat ve TX/RX hız uyumunu kontrol eder")
        p_ctrl = channel_prefix(ch) + "CTRL"
        has_ctrl = self.rm.is_loaded() and self.rm.has(p_ctrl)
        p_st = channel_prefix(ch) + "STATUS"
        has_rx_act = self.rm.is_loaded() and (self.rm.has(p_st) or self.rm.has(channel_prefix(ch) + "ACT_MIN_PULSE"))
        has_tx_act = self.rm.is_loaded() and (self.rm.has("TX_STATUS") or self.rm.has("TX_ACT_PULSE_DUR"))
        self.control_tab.chk_rx_en.setEnabled(conn and has_ctrl)
        self.control_tab.btn_clear_ch.setEnabled(conn and has_ctrl)
        self.control_tab.btn_refresh_stat.setEnabled(conn and has_ctrl)
        cfg_btn(
            self.control_tab.btn_check_rx, has_rx_act, [] if has_rx_act else [p_st],
            f"{channel_label(ch)} kanalının karttaki aktif config'ini (STATUS.ACT_CFG + ACT_*) okur ve karşılaştırır",
        )
        cfg_btn(
            self.control_tab.btn_check_tx, has_tx_act, [] if has_tx_act else ["TX_STATUS"],
            "TX kanalının karttaki aktif config'ini (TX_STATUS.ACT_CFG + TX_ACT_*) okur ve karşılaştırır",
        )
        has_tb = self.rm.is_loaded() and not self.rm.missing_for_rx_read("TB")
        has_chk = self.rm.is_loaded() and self.rm.has("TB_CHK_CTRL")
        self.tx_sent_tab.set_controls_enabled(self.connected, has_tb, has_chk, self.busy)
        tx_tip = (
            "Çevrimdışı modda kapalı (AXIL Studio Debug Bridge'den açın)." if not self.client
            else ("Debug Bridge karta bağlı değil." if not self.connected
                  else ("Eksik TX register'ları: " + ", ".join(tx_live_miss[:6]) if tx_live_miss else ""))
        )
        self.control_tab.tx_panel.set_io_enabled(conn and not tx_live_miss, tx_tip)
        self.btn_tx_live.setEnabled(True)
        self.btn_stop.setEnabled(self.busy)
        self.btn_show_bridge.setEnabled(self.client is not None)
        self.config_tab.btn_rx_add_cfg.setEnabled(self.client is not None and not rx_cfg_miss)
        self.config_tab.btn_tx_add_cfg.setEnabled(self.client is not None and not tx_cfg_miss)
        self.control_tab.update_map_summary(self.client, self.rm, ch)
        models_line = getattr(self.client, "models_line", True)
        if not self.client:
            tip = "Çevrimdışı modda kapalı (AXIL Studio Debug Bridge'den açın veya --cosim kullanın)."
        elif not self.connected:
            tip = "Debug Bridge karta bağlı değil."
        elif not models_line:
            tip = "Dahili simülatör ARINC hattını modellemez: kartta ya da --cosim (RTL) ile çalıştırın."
        elif not self.rm.grouped():
            tip = "Test IP 2.x register haritası gerektirir."
        else:
            tip = ""
        self.test_tab.set_controls(not tip, self.busy, tip)

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
        if getattr(self, "_selftest_running", False):
            self.test_tab.on_progress(done, total, msg)

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
        self.control_tab.tx_panel.refresh()
        self.control_tab.update_map_summary(self.client, self.rm, self.current_channel())
        self._recompare_cached_active_configs()
        for win in list(self._charts.values()):
            if win.isVisible():
                win.draw()
        self.read_tab.refresh()
        self.set_status("Config hesaplandı.")

    def _expected_rx_cfg(self) -> dict[str, int] | None:
        return dict(self.res.rx_values) if self.res else None

    def _expected_tx_cfg(self) -> dict[str, int] | None:
        if not self.res_tx:
            return None
        return {r: v for r, v in self.res_tx["writes"] if r.startswith("TX_CUST_")}

    def _recompare_cached_active_configs(self):
        if self._last_rx_act and self._last_rx_act.get("channel") == self.current_channel():
            self._last_rx_act = recompare_active_config(self._last_rx_act, self._expected_rx_cfg())
            self.control_tab.update_rx_active_config(self._last_rx_act)
            dlg = self._dialogs.get("rx_act_cfg")
            if isinstance(dlg, ActiveConfigDialog) and dlg.isVisible():
                dlg.update_info(self._last_rx_act)
        if self._last_tx_act:
            self._last_tx_act = recompare_active_config(self._last_tx_act, self._expected_tx_cfg())
            self.control_tab.update_tx_active_config(self._last_tx_act)
            dlg = self._dialogs.get("tx_act_cfg")
            if isinstance(dlg, ActiveConfigDialog) and dlg.isVisible():
                dlg.update_info(self._last_tx_act)

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

    def open_tx_driver_dialog(self):
        self._open_dialog("tx_driver", lambda: TxDriverDialog(self))

    def open_tx_fpga_dialog(self):
        self._open_dialog("tx_fpga", lambda: TxFpgaDialog(self))

    def open_chart(self, kind: str, case: str):
        win = self._charts.get((kind, case))
        if win is not None and win.isVisible():
            win.raise_()
            win.activateWindow()
            return
        win = ChartWindow(self, kind, case)
        self._charts[(kind, case)] = win
        win.show()

    def open_tx_live(self):
        self.control_tab.popout_tx()

    # ================================================================ Debug Bridge config listesi
    def add_rx_to_bridge_config(self):
        if not self.client or not self.res:
            return
        ch = self.current_channel()
        p = channel_prefix(ch)
        rows = [(p + "CFG_SEL", 2)] + [(p + k, v) for k, v in self.res.rx_values.items()] + [(p + "CFG_APPLY", 1)]
        rows = bridge_rows(self.rm, rows)
        self.bus.run(
            lambda: self.client.add_config(rows),
            ok=lambda _: self.set_status(f"{channel_label(ch)} RX Config Debug Bridge listesine eklendi."),
            err=lambda e: QMessageBox.warning(self, APP, str(e)),
        )

    def add_tx_to_bridge_config(self):
        if not self.client or not self.res_tx:
            return
        rows = bridge_rows(self.rm, self.res_tx["writes"])
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
        self.prog.setRange(0, 100)
        self.prog.setValue(0)
        self._update_controls()
        self.set_status(f"{title}…")

        def ok(result):
            self.busy = False
            if show_progress:
                self.prog.setValue(self.prog.maximum())
            self._flush_write_log()
            self._update_controls()
            self.set_status(f"{title}: tamam.")
            if on_ok:
                on_ok(result)
            if on_done:
                on_done(True)

        def fail(exc):
            self.busy = False
            self.prog.setValue(0)
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

        self._run_job(
            f"{channel_label(ch)} RX Config gönderiliyor",
            job,
            on_ok=lambda _: self.do_check_rx_config(show_dialog=False),
        )

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
            sm = data.get("summary", {})
            self.control_tab.set_last_read_summary(
                f"Son okuma ({channel_label(ch)}): {len(data.get('words', []))} Word, "
                f"{len(data.get('errors', []))} Error, {len(data.get('bits', [])) // 32} Word Bit Diag"
            )
            self.control_tab.update_live_stats({
                "enable": self.control_tab.chk_rx_en.isChecked(),
                "word_cnt": sm.get("total_word_cnt"),
                "err_cnt": sm.get("total_error_cnt"),
                "drop_cnt": sm.get("drop_cnt"),
                "last_word": data["words"][0]["w"][2] if data.get("words") else None,
            })
            self.tabs.setCurrentWidget(self.read_tab)

        self._run_job(f"{channel_label(ch)} RX verileri okunuyor", job, on_ok=done, show_progress=True)

    def do_refresh_status(self):
        if not self.connected or self.busy:
            return
        ch = self.current_channel()
        rm = self.rm
        if not rm.has(channel_prefix(ch) + "CTRL"):
            self.control_tab.update_live_stats(None)
        else:
            self.bus.run(
                lambda: read_channel_status(self.client, rm, ch, quiet=True),
                ok=lambda info: self.control_tab.update_live_stats(info),
                err=lambda e: self.log(f"Durum okunamadı ({ch}): {e}"),
            )
        self.do_check_rx_config(show_dialog=False)

    def _show_active_config_dialog(self, key: str, info: dict, on_refresh, on_send):
        dlg = self._dialogs.get(key)
        if isinstance(dlg, ActiveConfigDialog) and dlg.isVisible():
            dlg.update_info(info)
            dlg.raise_()
            dlg.activateWindow()
            return
        dlg = ActiveConfigDialog(self, info, on_refresh=on_refresh, on_send=on_send)
        self._dialogs[key] = dlg
        dlg.show()

    def do_check_rx_config_dialog(self):
        self.do_check_rx_config(show_dialog=True)

    def do_check_rx_config(self, show_dialog: bool = False):
        if not self.connected or self.busy:
            if not self.connected:
                self.control_tab.update_rx_active_config(None)
            return
        ch = self.current_channel()
        rm = self.rm
        p = channel_prefix(ch)
        if not (rm.has(p + "STATUS") or rm.has(p + "ACT_MIN_PULSE")):
            self.control_tab.update_rx_active_config(None)
            return
        exp = self._expected_rx_cfg()

        def ok(info: dict):
            if ch != self.current_channel():
                return
            self._last_rx_act = info
            self.control_tab.update_rx_active_config(info)
            if show_dialog:
                st = (
                    "Arayüzdeki Config ile tam eşleşiyor."
                    if info["all_match"]
                    else f"{info['mismatch']} parametre arayüzden farklı."
                )
                self.log(f"[{channel_label(ch)} Aktif Config] {info['mode_name']} — {st}")
                self._show_active_config_dialog(
                    "rx_act_cfg",
                    info,
                    on_refresh=lambda: self.do_check_rx_config(show_dialog=True),
                    on_send=self.do_send_rx_cfg,
                )
            else:
                dlg = self._dialogs.get("rx_act_cfg")
                if isinstance(dlg, ActiveConfigDialog) and dlg.isVisible():
                    dlg.update_info(info)

        def fail(exc):
            if show_dialog:
                QMessageBox.warning(self, f"{channel_label(ch)} Aktif Config", str(exc))
            else:
                self.log(f"Aktif RX config okunamadı ({ch}): {exc}")

        self.bus.run(
            lambda: read_rx_active_config(self.client, rm, ch, expected=exp, quiet=not show_dialog),
            ok=ok,
            err=fail,
        )

    def do_check_tx_config_dialog(self):
        self.do_check_tx_config(show_dialog=True)

    def do_check_tx_config(self, show_dialog: bool = False):
        if not self.connected or self.busy:
            if not self.connected:
                self.control_tab.update_tx_active_config(None)
            return
        rm = self.rm
        if not (rm.has("TX_STATUS") or rm.has("TX_ACT_PULSE_DUR")):
            self.control_tab.update_tx_active_config(None)
            return
        exp = self._expected_tx_cfg()

        def ok(info: dict):
            self._last_tx_act = info
            self.control_tab.update_tx_active_config(info)
            if show_dialog:
                st = (
                    "Arayüzdeki Config ile tam eşleşiyor."
                    if info["all_match"]
                    else f"{info['mismatch']} parametre arayüzden farklı."
                )
                self.log(f"[TX Aktif Config] {info['mode_name']} — {st}")
                self._show_active_config_dialog(
                    "tx_act_cfg",
                    info,
                    on_refresh=lambda: self.do_check_tx_config(show_dialog=True),
                    on_send=self.do_send_tx_cfg,
                )
            else:
                dlg = self._dialogs.get("tx_act_cfg")
                if isinstance(dlg, ActiveConfigDialog) and dlg.isVisible():
                    dlg.update_info(info)

        def fail(exc):
            if show_dialog:
                QMessageBox.warning(self, "TX Aktif Config", str(exc))
            else:
                self.log(f"Aktif TX config okunamadı: {exc}")

        self.bus.run(
            lambda: read_tx_active_config(self.client, rm, expected=exp, quiet=not show_dialog),
            ok=ok,
            err=fail,
        )

    # ------------------------------------------------------------- IP durum kontrolü
    def do_check_ip_dialog(self):
        self.do_check_ip(show_dialog=True)

    def do_check_ip(self, show_dialog: bool = False):
        """IP'yi kontrol eder (logger enable/freeze, hat teşhisi, sürüm, saat, hız uyumu)."""
        if not self.connected:
            if show_dialog:
                QMessageBox.information(self, "IP Durumu", "Debug Bridge bağlı değil.")
            return
        if self.busy:
            return
        rm = self.rm
        clk_hz = int(round(self.ci.clk_mhz * 1e6)) if self.ci.clk_mhz else None

        def ok(res: dict):
            first = self._last_health is None
            self._last_health = res
            self.control_tab.update_health(res)
            bad = [f for f in res["findings"] if f["level"] in ("error", "warn")]
            if (first or show_dialog) and bad:
                self.log(f"[IP Durumu] {len(bad)} sorun: " + "; ".join(f"[{f['area']}] {f['title']}" for f in bad[:4]))
            dlg = self._dialogs.get("ip_health")
            if show_dialog:
                if isinstance(dlg, IpHealthDialog) and dlg.isVisible():
                    dlg.update_result(res)
                    dlg.raise_()
                    dlg.activateWindow()
                else:
                    dlg = IpHealthDialog(self, res, on_refresh=lambda: self.do_check_ip(show_dialog=True),
                                         on_fix=self.do_ip_fix)
                    self._dialogs["ip_health"] = dlg
                    dlg.show()
            elif isinstance(dlg, IpHealthDialog) and dlg.isVisible():
                dlg.update_result(res)

        def fail(exc):
            self.log(f"IP durumu kontrol edilemedi: {exc}")
            if show_dialog:
                QMessageBox.warning(self, "IP Durumu", str(exc))

        self.bus.run(lambda: check_ip(self.client, rm, clk_hz=clk_hz), ok=ok, err=fail)

    def do_ip_fix(self, fixes: list[tuple]):
        rm = self.rm

        def job():
            for fx in fixes:
                apply_fix(self.client, rm, fx, log=self.log, on_write=self._record_write)

        def after(_):
            dlg = self._dialogs.get("ip_health")
            self.do_refresh_status()
            self.do_check_ip(show_dialog=isinstance(dlg, IpHealthDialog) and dlg.isVisible())

        self._run_job("IP durumu düzeltiliyor", job, on_ok=after)

    def do_toggle_rx_enable(self, enable: bool):
        if not self.connected:
            return
        ch = self.current_channel()
        rm = self.rm
        self._run_job(
            f"{channel_label(ch)} Logger {'açılıyor' if enable else 'kapatılıyor'}",
            lambda: set_channel_enable(self.client, rm, ch, enable, log=self.log, on_write=self._record_write),
            on_ok=lambda _: (self.do_refresh_status(), self.do_check_ip()),
        )

    def do_clear_channel(self):
        ch = self.current_channel()
        if not look.confirm(self, APP, f"{channel_label(ch)} kanalının Word/Error sayaçları temizlensin mi?", "Temizle"):
            return
        rm = self.rm
        self._run_job(
            f"{channel_label(ch)} sayaçları temizleniyor",
            lambda: clear_channel(self.client, rm, ch, log=self.log, on_write=self._record_write),
            on_ok=lambda _: self.do_refresh_status(),
        )

    def record_tx_event(self, cat: str, kind: str, word: int | None = None, detail: str = "", ok: bool = True):
        now = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self.tx_history.append({"time": now, "cat": cat, "kind": kind, "word": word, "detail": detail, "ok": ok})
        if len(self.tx_history) > 2000:
            self.tx_history = self.tx_history[-2000:]
        self.tx_sent_tab.refresh_history()
        self.mark_dirty()
        if ok and self.connected:
            QTimer.singleShot(80, self.do_refresh_tx_bit)

    def do_refresh_tx_bit(self):
        if not self.connected or self.busy:
            if not self.connected:
                self.tx_sent_tab.update_tx_bit_status(None)
            return
        rm = self.rm
        if not any(rm.has(r) for r in ("TX_WORD_CNT", "TB_WORD_CNT", "TB_CHK_CTRL")):
            self.tx_sent_tab.update_tx_bit_status(None)
            return
        self.bus.run(
            lambda: read_tx_bit_status(self.client, rm, quiet=True),
            ok=lambda info: self.tx_sent_tab.update_tx_bit_status(info),
            err=lambda e: self.log(f"TX BIT durumu okunamadı: {e}"),
        )

    def do_apply_tx_checker(self, enable: bool, timeout_clk: int):
        rm = self.rm
        self._run_job(
            "TX BIT Checker ayarları yazılıyor",
            lambda: set_tx_checker(self.client, rm, enable, timeout_clk, log=self.log, on_write=self._record_write),
            on_ok=lambda _: self.do_refresh_tx_bit(),
        )

    def do_clear_tx_checker_fifo(self):
        rm = self.rm
        self._run_job(
            "TX BIT Checker FIFO temizleniyor",
            lambda: clear_tx_checker_fifo(self.client, rm, log=self.log, on_write=self._record_write),
            on_ok=lambda _: self.do_refresh_tx_bit(),
        )

    def do_read_tx_bit(self):
        self.recalc()
        if not self.res:
            return
        opts = copy.deepcopy(self.rs)
        rm = self.rm
        mhz = self.ci.clk_mhz

        def job():
            return read_channel(
                self.client, rm, "TB", opts,
                progress=lambda d, t, m: self._prog_sig.emit(d, t, m),
                stop_flag=self._stop_flag,
                log=self.log,
                on_write=self._record_write,
            )

        def done(data):
            s = P.new_session(data, self.ci, self.rs, self.ds)
            s["clk_mhz"] = mhz
            self.add_session(s, save_file=True)
            self.do_refresh_tx_bit()
            self.tabs.setCurrentWidget(self.read_tab)

        self._run_job("TX BIT (TB) verileri okunuyor", job, on_ok=done, show_progress=True)

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
            self.do_check_rx_config(show_dialog=False)
            self.tabs.setCurrentWidget(self.read_tab)

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

        self._run_job(
            "TX Config gönderiliyor",
            job,
            on_ok=lambda _: self.do_check_tx_config(show_dialog=False),
        )

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

    def tx_scheduler_write(self, enable: bool, writes: list[tuple[str, int]], on_result=None) -> bool:
        """Scheduler başlatırken öncesinde, durdururken sonrasında TX_WORD_CNT okur; on_result(ok, word_cnt)."""
        if not self.connected:
            QMessageBox.information(self, APP, "Debug Bridge bağlı değil (çevrimdışı modda yazma yapılamaz).")
            return False
        miss = self.rm.missing([r for r, _ in writes])
        if miss:
            QMessageBox.warning(self, APP, "IP haritasında eksik TX register'ları:\n" + ", ".join(miss))
            return False
        rm = self.rm
        has_cnt = rm.has("TX_WORD_CNT")
        cnt_off = rm.offset("TX_WORD_CNT") if has_cnt else None

        def job():
            cnt = self.client.read(cnt_off, quiet=True) if (enable and has_cnt) else None
            ip_tx_write(self.client, rm, writes, verify=True, quiet=False, log=self.log, on_write=self._record_write)
            if not enable and has_cnt:
                cnt = self.client.read(cnt_off, quiet=True)
            return cnt

        def ok_cb(cnt):
            if on_result:
                on_result(True, cnt)

        def done_cb(ok):
            if not ok and on_result:
                on_result(False, None)

        title = "TX Scheduler " + ("başlatılıyor" if enable else "durduruluyor")
        return self._run_job(title, job, on_ok=ok_cb, on_done=done_cb)

    # ------------------------------------------------------------- Loopback test
    def do_run_selftest(self, opts: dict):
        from .. import selftest
        if not self.connected or self.busy:
            return
        rm = self.rm
        self.recalc()
        custom = None
        if self.res and self.res_tx and self.res.rx_values:
            custom = {"rx": dict(self.res.rx_values), "tx": list(self.res_tx["writes"])}
        self.log(f"[Test] Loopback testi başlıyor: TX → {', '.join(opts['rx']) or '—'}"
                 + (" + TX BIT" if opts["tb"] else "") + f", hızlar {'/'.join(opts['speeds'])}")
        self._selftest_running = True

        def job():
            return selftest.run(
                self.client, rm, opts["rx"], selected=opts["selected"], speeds=opts["speeds"], use_tb=opts["tb"],
                pattern_len=opts["pattern_len"], burst_words=opts["burst_words"], custom=custom,
                stop_on_fail=opts["stop_on_fail"], log=self.log, stop=self._stop_flag,
                progress=lambda d, t, m: self._prog_sig.emit(d, t, m),
                on_result=lambda r: self._test_sig.emit(r),
            )

        def done(rep):
            self._selftest_running = False
            self.test_tab.set_report(rep)
            c = rep["counts"]
            self.log(f"[Test] {'GEÇTİ' if rep['passed'] else 'KALDI'}: PASS {c['PASS']}, FAIL {c['FAIL']}, "
                     f"ERROR {c['ERROR']}, SKIP {c['SKIP']} ({rep['duration_s']} s)")
            self.do_refresh_status()
            self.do_check_tx_config(show_dialog=False)
            self.do_check_ip()

        def finished(ok):
            if not ok:
                self._selftest_running = False
                self.test_tab.set_report(None, "Test koşturulamadı (İşlem Logu'na bakın)")

        self._run_job("Loopback testi", job, on_ok=done, on_done=finished, show_progress=True)
        self._update_controls()

    def do_ip_reset(self):
        if not look.confirm(self, APP, "ARINC 429 IP bloğu resetlensin mi? (SOFT_RESET.ALL darbesi gönderilir)", "Resetle"):
            return
        rm = self.rm

        def after_reset(_):
            self.do_refresh_status()
            self.do_check_tx_config(show_dialog=False)
            self.do_refresh_tx_bit()
            self.do_check_ip()

        self._run_job(
            "IP reset",
            lambda: soft_reset(self.client, rm, "ALL", log=self.log, on_write=self._record_write),
            on_ok=after_reset,
        )

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
        self.tx_sent_tab.refresh_tb_session()

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
        self.tx_sent_tab.refresh_tb_session()

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
        self.sessions, self.tx_history, self.cur_session, self.project_path, self.dirty = [], [], None, None, False
        self.config_tab.load_from_model()
        self.control_tab.load_from_model()
        self.read_tab.load_settings()
        self.recalc()
        self.read_tab.refresh_sessions()
        self.tx_sent_tab.refresh_history()
        self.tx_sent_tab.refresh_tb_session()
        self._update_header()

    def open_project(self):
        if not self._confirm_discard():
            return
        p, _ = QFileDialog.getOpenFileName(self, "Proje aç", "", "ARINC429 proje (*.a429proj);;Tümü (*.*)")
        if not p:
            return
        try:
            self.ci, self.rs, self.ds, self.sessions = P.load_project(p)
            self.tx_history = P.load_tx_history(p)
            self.rs.out_dir = native_dir(self.rs.out_dir)
        except Exception as e:
            QMessageBox.critical(self, APP, f"Proje açılamadı:\n{e}")
            return
        self.project_path, self.dirty = p, False
        self.cur_session = self.sessions[-1] if self.sessions else None
        self.config_tab.load_from_model()
        self.control_tab.load_from_model()
        self.read_tab.load_settings()
        self.recalc()
        self.read_tab.refresh_sessions()
        self.tx_sent_tab.refresh_history()
        self.tx_sent_tab.refresh_tb_session()
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
            P.save_project(p, self.ci, self.rs, self.ds, self.sessions, tx_history=self.tx_history)
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
            old_out = self.rs.out_dir
            self.ci, self.rs, self.ds = P.load_config(p)
            self.rs.out_dir = native_dir(self.rs.out_dir or old_out)
        except Exception as e:
            QMessageBox.critical(self, APP, f"Config açılamadı:\n{e}")
            return
        self.config_tab.load_from_model()
        self.control_tab.load_from_model()
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
        self.control_tab.close_floating()
        if self.client is not None:
            self.client.on_event = lambda _: None
        super().closeEvent(ev)
