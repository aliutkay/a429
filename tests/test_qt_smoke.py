"""Qt arayüz duman testleri (QT_QPA_PLATFORM=offscreen)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from a429.qt import look
from a429.qt.main_window import MainWindow
from a429.sim import SimClient


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
    for _ in range(100):
        app.processEvents()
        if not win.busy:
            break
    win.control_tab.tx_panel.manual_send()
    for _ in range(100):
        app.processEvents()
        if not win.busy:
            break
    assert len(win.tx_history) == 2
    assert win.tx_sent_tab.tv_hist._model.rowCount() == 2

    # Scheduler başlat/durdur -> Δ TX_WORD_CNT kaydedilmeli
    win.control_tab.tx_panel.toggle_scheduler()
    for _ in range(100):
        app.processEvents()
        if not win.busy:
            break
    win.control_tab.tx_panel.toggle_scheduler()
    for _ in range(100):
        app.processEvents()
        if not win.busy:
            break
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
