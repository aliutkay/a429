"""ARINC 429 Test Aracı – AXIL Studio IP arayüzü ve çevrimdışı başlatıcı.

Kullanım:
  AXIL Studio Debug Bridge'den otomatik başlatılır (AXIL_STUDIO_PORT / AXIL_STUDIO_TOKEN).
  Bağımsız (çevrimdışı) mod:   python a429_ui.py
  Simülatör modu:              python a429_ui.py --sim
"""
from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox


def _connect_studio():
    """AXIL Studio ortam değişkenleri varsa bağlanır; yoksa None (çevrimdışı) döner."""
    if not (os.environ.get("AXIL_STUDIO_PORT") and os.environ.get("AXIL_STUDIO_TOKEN")):
        return None
    from axil_client import AxilClient
    return AxilClient.from_env("ARINC 429 arayüzü")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ARINC 429 Test Aracı (AXIL Studio IP arayüzü)")
    parser.add_argument("--sim", action="store_true", help="AXIL Studio olmadan dahili IP simülatörüyle aç")
    parser.add_argument("--quit-after", type=int, default=0, help="Belirtilen ms sonra otomatik kapat (test için)")
    args, qt_args = parser.parse_known_args(argv)

    app = QApplication([sys.argv[0]] + qt_args)
    app.setApplicationName("ARINC 429 Test Aracı")

    # matplotlib kontrolü (Studio'nun Python ortamında kurulu olmayabilir)
    try:
        import matplotlib  # noqa: F401
    except ImportError:
        QMessageBox.critical(
            None,
            "ARINC 429 Test Aracı",
            "Bu arayüz için 'matplotlib' kütüphanesi gereklidir.\n\n"
            f"Lütfen AXIL Studio'nun kullandığı Python ortamına kurun:\n{sys.executable} -m pip install matplotlib",
        )
        return 2

    from a429.qt import look
    from a429.qt.main_window import MainWindow

    client = None
    if args.sim:
        from a429.sim import SimClient
        client = SimClient()
    else:
        try:
            client = _connect_studio()
        except Exception as exc:
            QMessageBox.critical(
                None,
                "ARINC 429 Test Aracı",
                f"AXIL Studio Debug Bridge'e bağlanılamadı:\n\n{exc}",
            )
            return 2

    look.apply(app, client.theme if client else None)
    win = MainWindow(client)
    win.show()

    if args.quit_after > 0:
        QTimer.singleShot(args.quit_after, app.quit)

    code = app.exec()
    win.bus.shutdown()
    if client is not None:
        client.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
