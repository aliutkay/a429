"""Qt arayüz duman testleri (QT_QPA_PLATFORM=offscreen)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from a429.qt import look
from a429.qt.main_window import MainWindow
from a429.sim import SimClient


def _wait(app, win, timeout_s: float = 5.0):
    """Arka plan işi (Worker) bitene kadar olayları işler."""
    import time
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        app.processEvents()
        if not win.busy and win.bus.pending == 0:
            break
        time.sleep(0.002)
    app.processEvents()


def _app():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
        look.apply(app)
    return app


def test_offline_window_smoke():
    app = _app()
    win = MainWindow(client=None)
    assert not win.connected
    assert not win.btn_send_rx.isEnabled()
    assert not win.btn_read_rx.isEnabled()
    assert not win.btn_send_tx.isEnabled()
    assert not win.btn_reset.isEnabled()
    assert not win.control_tab.btn_check_rx.isEnabled()
    assert not win.control_tab.btn_check_tx.isEnabled()
    assert win.res is not None
    assert win.config_tab.tv_rx_regs.rowCount() == 8
    win._closing = True
    win.close()
    win.bus.shutdown()
    app.processEvents()


def test_sim_window_read_and_dialogs(tmp_path):
    app = _app()
    sim = SimClient(num_rx=2, has_tx=True, has_txbit=True)
    win = MainWindow(client=sim)
    win.rs.out_dir = str(tmp_path)
    assert win.connected
    assert win.btn_send_rx.isEnabled()
    assert win.btn_read_rx.isEnabled()
    assert win.btn_send_tx.isEnabled()
    assert win.cb_channel.count() == 3  # RX0, RX1, TB

    # RX Config gönder + oku (worker tamamlanana kadar olayları işle)
    win.do_all()
    for _ in range(200):
        app.processEvents()
        if not win.busy:
            break
    assert not win.busy
    assert len(win.sessions) == 1
    assert win.read_tab.tv_word._model.rowCount() == 23
    assert win.read_tab.tv_err._model.rowCount() == 3

    # TX Canlı Kontrol varsayılan olarak gömülü, istenince ayrılıp geri alınabilir
    assert not win.control_tab.tx_popped_out
    assert win.control_tab.tx_card.isVisibleTo(win.control_tab)
    win.open_tx_live()
    assert win.control_tab.tx_popped_out
    assert not win.control_tab.tx_card.isVisibleTo(win.control_tab)
    win.control_tab._tx_win.close()
    assert not win.control_tab.tx_popped_out
    assert win.control_tab.tx_card.isVisibleTo(win.control_tab)

    # TX Line Driver ve TX FPGA diyalogları + TX grafik penceresi
    win.open_tx_driver_dialog()
    assert win._dialogs["tx_driver"].isVisible()
    win._dialogs["tx_driver"].close()
    win.open_tx_fpga_dialog()
    assert win._dialogs["tx_fpga"].isVisible()
    win._dialogs["tx_fpga"].close()
    win.open_chart("tx_single", "NOM")
    assert win._charts[("tx_single", "NOM")].isVisible()
    win._charts[("tx_single", "NOM")].close()
    win.open_chart("tx_example", "NOM")
    assert win._charts[("tx_example", "NOM")].isVisible()
    win._charts[("tx_example", "NOM")].close()

    # TX Canlı Kontrol'den Word Yaz + Tek Gönder -> TX Gönderilen Veriler tablosuna eklenmeli
    win.control_tab.tx_panel.write_word()
    _wait(app, win)
    win.control_tab.tx_panel.manual_send()
    _wait(app, win)
    assert len(win.tx_history) == 2
    assert win.tx_sent_tab.tv_hist._model.rowCount() == 2

    # Scheduler başlat/durdur -> Δ TX_WORD_CNT kaydedilmeli
    win.control_tab.tx_panel.toggle_scheduler()
    _wait(app, win)
    win.control_tab.tx_panel.toggle_scheduler()
    _wait(app, win)
    assert win.tx_history[-1]["kind"] == "Scheduler ⏸"
    assert "Δ TX_WORD_CNT" in win.tx_history[-1]["detail"]

    # TX BIT okuması ve RX'te açma
    win.do_read_tx_bit()
    for _ in range(200):
        app.processEvents()
        if not win.busy:
            break
    assert win.tx_sent_tab._tb_session is not None
    assert win.tx_sent_tab.tv_tb_err._model.rowCount() == 1

    # Kanal değiştir (TB)
    idx = win.cb_channel.findData("TB")
    assert idx >= 0
    win.cb_channel.setCurrentIndex(idx)
    assert win.current_channel() == "TB"

    # Karttaki aktif RX ve TX config kontrol pencereleri
    win.do_check_rx_config(show_dialog=True)
    win.do_check_tx_config(show_dialog=True)
    for _ in range(120):
        app.processEvents()
        if "rx_act_cfg" in win._dialogs and "tx_act_cfg" in win._dialogs:
            break
    assert win._dialogs["rx_act_cfg"].isVisible()
    assert win._dialogs["tx_act_cfg"].isVisible()
    assert "High Speed" in win.control_tab.rx_cfg_pill.text()
    win._dialogs["rx_act_cfg"].close()
    win._dialogs["tx_act_cfg"].close()

    win._closing = True
    win.close()
    win.bus.shutdown()
    app.processEvents()


def test_ip_health_check_ui_and_fix():
    app = _app()
    sim = SimClient()
    win = MainWindow(sim)
    win.show()
    _wait(app, win)
    win.do_check_ip()
    _wait(app, win)
    res = win._last_health
    assert res is not None and res["worst"] == "error"          # RX0 / TB logger reset sonrası kapalı
    assert "hata" in win.control_tab.health_pill.text()
    win.do_refresh_status()
    _wait(app, win)
    assert win.control_tab.rx_warn.isVisibleTo(win.control_tab)
    assert "Logger kapalı" in win.control_tab.lbl_rx_warn.text()

    win.do_check_ip_dialog()
    _wait(app, win)
    dlg = win._dialogs["ip_health"]
    assert dlg.isVisible() and dlg.btn_fix_all.isVisible()
    dlg._fix_all()
    _wait(app, win)
    _wait(app, win)
    assert sim.read(win.rm.offset("RX0_CTRL")) & 1
    assert win._last_health["counts"]["error"] == 0
    assert not win.control_tab.rx_warn.isVisibleTo(win.control_tab)

    sim.sim_line["RX0"] = (1, 1)
    win.do_refresh_status()
    _wait(app, win)
    assert "Hat 11" in win.control_tab.lbl_rx_warn.text()
    dlg.close()
    win._closing = True
    win.close()


def test_test_tab_disabled_on_sim_and_runs_on_rtl():
    app = _app()
    win = MainWindow(SimClient())
    win.show()
    _wait(app, win)
    assert win.tabs.indexOf(win.test_tab) >= 0
    assert not win.test_tab.btn_run.isEnabled()
    assert "simülatör" in win.test_tab.btn_run.toolTip()
    win._closing = True
    win.close()

    from a429 import cosim
    if not cosim.available():
        return
    cl = cosim.CosimClient()
    win = MainWindow(cl)
    win.show()
    _wait(app, win)
    assert win.test_tab.btn_run.isEnabled()
    assert list(win.test_tab._rx_boxes) == ["RX0"]
    from PySide6.QtCore import Qt
    for i in range(win.test_tab.lst.count()):          # hızlı alt küme: tek Word + parity (+ zorunlu kimlik/hazırlık)
        it = win.test_tab.lst.item(i)
        if it.data(Qt.ItemDataRole.UserRole) not in ("single", "parity") and it.flags() & Qt.ItemFlag.ItemIsEnabled:
            it.setCheckState(Qt.CheckState.Unchecked)
    win.test_tab.chk_ls.setChecked(False)
    win.test_tab._run()
    _wait(app, win, 120)
    rep = win.test_tab.report
    assert rep is not None and rep["passed"], rep
    assert [r.tid for r in rep["results"]] == ["ident", "prep", "single", "parity"]
    assert win.test_tab.tree.topLevelItemCount() == 4
    win._closing = True
    win.close()
    win.bus.shutdown()
    cl.close()


def test_test_tab_ballard_mode_ui():
    from a429.ballard import CardInfo

    app = _app()
    win = MainWindow(SimClient(num_rx=2, has_tx=True, has_txbit=True))
    win.show()
    _wait(app, win)
    tt = win.test_tab
    assert tt.mode() == "loopback"
    assert tt.mode_stack.currentIndex() == 0
    assert tt.list_stack.currentIndex() == 0
    assert tt.result_stack.currentIndex() == 0

    tt.set_mode("ballard")
    assert tt.mode() == "ballard"
    assert tt.mode_stack.currentIndex() == 1
    assert tt.list_stack.currentIndex() == 1
    assert tt.result_stack.currentIndex() == 1

    card = CardInfo(
        card_num=0, core_num=0, product="BUSBox BB1120", card_type="BUSBOX",
        rx_channels=[0, 1, 2, 3], tx_channels=[4, 5], serial=112042,
    )
    tt.set_ballard_probe_result([card], dll_path="BTICARD64.DLL")
    assert tt.cb_bb_rx_ch.count() == 4
    assert tt.cb_bb_tx_ch.count() == 2
    opts = tt.options()
    assert opts["mode"] == "ballard"
    assert opts["card_num"] == 0 and opts["core_num"] == 0
    assert opts["bb_rx_chan"] == 0 and opts["bb_tx_chan"] == 4
    assert opts["rx"] == ["RX0"]
    assert "tx_period" in opts["selected"] and "duplex" in opts["selected"]

    tt.set_mode("loopback")
    assert tt.options()["mode"] == "loopback"
    assert tt.result_stack.currentIndex() == 0

    win._closing = True
    win.close()
    win.bus.shutdown()
    app.processEvents()


def test_test_tab_pcs_mode_ui():
    from a429.pcs_test import PcsInfo

    app = _app()
    win = MainWindow(SimClient(num_rx=2, has_tx=True, has_txbit=True))
    win.show()
    _wait(app, win)
    tt = win.test_tab

    tt.set_mode("pcs")
    assert tt.mode() == "pcs"
    assert tt.mode_stack.currentIndex() == 2
    assert tt.list_stack.currentIndex() == 2
    assert tt.result_stack.currentIndex() == 2
    assert not tt.common_box.isVisibleTo(tt)
    assert tt.btn_pcs_start.isVisibleTo(tt)
    assert tt.btn_pcs_inspect.isVisibleTo(tt)

    pi = PcsInfo(name="PCS_A429", base=0x00000000, is_ip_parent=True, pcs_id=0x5EC00200, imem_aw=10, dmem_aw=8)
    tt.set_pcs_probe_result([pi])
    assert "1024" in tt.lbl_pcs_size.text()
    opts = tt.options()
    assert opts["mode"] == "pcs"
    assert opts["pcs_base"] == 0
    assert opts["pcs_name"] == "PCS_A429"
    assert opts["stop_on_fail"] is False
    assert len(opts["selected"]) == 15

    telem = {
        "mode": "pcs", "timestamp": "2026-01-01 00:00:00", "pcs_base": 0, "pcs_id": 0x5EC00200,
        "imem_size": 1024, "dmem_size": 256, "imem_cnt": 562, "pcs_state": "RUNNING", "pcs_busy": True,
        "pcs_err": False, "pcs_pc": 42, "pcs_err_code": 0, "pcs_err_text": "", "pcs_err_pc": 0,
        "pcs_err_addr": 0, "recognized": True, "signature": 0xA4292101, "run_state": "KOŞUYOR",
        "halted_on_fail": False, "stop_on_fail": False,
        "clk_hz": 50_000_000, "ip_base": 0x00010000, "gap_ms": 500.0, "max_rounds": 0,
        "total_rounds": 10, "pass_rounds": 9, "fail_rounds": 1, "pass_rate_pct": 90.0, "consec_pass": 6,
        "last_round_failed": False, "last_dur_ms": 12.5, "max_noise_clk": 0,
        "tests": [{"idx": 0, "tid": "ident", "title": "IP kimliği", "hint": "", "fails": 1, "last_failed": False, "ever_failed": True, "fail_channels": ["RX0"]}],
        "channels": [{"idx": 0, "code": 0, "name": "RX0", "fails": 1}],
        "first_fail": {"round": 4, "test_idx": 3, "test_id": "single_hs", "test_title": "HS Tek Word",
                       "channel": "RX0", "channel_code": 0, "sub_code": 10, "reason": "LAST_WORD uyuşmadı",
                       "expected": 0x12345678, "got": 0x12345679},
        "last_fail": {"round": 4, "test_idx": 3, "test_id": "single_hs", "test_title": "HS Tek Word",
                      "channel": "RX0", "channel_code": 0, "sub_code": 10, "reason": "LAST_WORD uyuşmadı",
                      "expected": 0x12345678, "got": 0x12345679},
        "passed": False,
    }
    tt.set_pcs_telemetry(telem)
    win._sync_pcs_control_state(telem)
    assert tt.pcs_tree.topLevelItemCount() == 1
    assert tt.pcs_tree.topLevelItem(0).text(0) == "GEÇTİ"
    assert tt.pcs_ch_tree.topLevelItemCount() == 1
    assert "10 tur" in tt.pill.text()
    assert tt.pill.property("state") == "ok"
    assert "9" in tt.pill_pcs_pass.text()
    assert "1" in tt.pill_pcs_fail.text()
    assert "90.0%" in tt.pill_pcs_rate.text()
    assert "6" in tt.pill_pcs_streak.text()
    assert "Tur #4" in tt.txt_pcs_log.toPlainText()
    assert win.control_tab.outdated_bar.isVisibleTo(win.control_tab)

    tt.stop_pcs_poll()
    win._closing = True
    win.close()
    win.bus.shutdown()
    app.processEvents()



