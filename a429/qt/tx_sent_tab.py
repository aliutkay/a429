"""TX Gönderilen Veriler sekmesi (yer tutucu)."""
from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from . import look


class TxSentTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.addWidget(look.label("TX gönderilen veriler burada listelenecek (sonraki aşama).", "cardTitle"))
        lay.addWidget(look.label(
            "İleride TX_WORD_CNT ve TX BIT kanalı (TB_) kayıtları ile gönderilen Word geçmişi burada gösterilecektir.",
            "muted",
            wrap=True,
        ))
        lay.addStretch(1)
