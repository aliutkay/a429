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

    # TX Canlı Kontrol penceresini aç
    win.open_tx_live()
    assert win._tx_win is not None and win._tx_win.isVisible()
    win._tx_win.close()

    # Kanal değiştir (TB)
    idx = win.cb_channel.findData("TB")
    assert idx >= 0
    win.cb_channel.setCurrentIndex(idx)
    assert win.current_channel() == "TB"

    win._closing = True
    win.close()
    win.bus.shutdown()
    app.processEvents()
