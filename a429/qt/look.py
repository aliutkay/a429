"""AXIL Studio tema uyumu ve ortak Qt widget yardımcıları."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

FALLBACK = {
    "bg": "#F2F4F8", "surface": "#FFFFFF", "surface2": "#EEF1F7", "border": "#D3DAE6", "text": "#1A1A1A",
    "muted": "#5A6475", "accent": "#003087", "accent_text": "#FFFFFF", "accent_soft": "#E5EAF3",
    "primary": "#003087", "primary_hover": "#33599F", "hover": "#E6EAF2", "selection": "#CCD6E7",
    "danger": "#C62828", "success": "#2E7D32", "warning": "#F7931D", "input": "#FFFFFF",
    "row": "#F6F7FA", "row_alt": "#ECEFF5",
}
_tokens = dict(FALLBACK)
_dark = False


def tokens() -> dict:
    return _tokens


def is_dark() -> bool:
    return _dark


def color(name: str) -> QColor:
    return QColor(_tokens.get(name, FALLBACK.get(name, "#000000")))


def mono_font(delta: float = 0) -> QFont:
    f = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    f.setPointSizeF(max(7.0, f.pointSizeF() + delta))
    return f


def apply(app, theme: dict | None = None):
    """AXIL Studio tema paketini ({"dark": bool, "tokens": {...}}) uygular."""
    global _tokens, _dark
    if theme and theme.get("tokens"):
        _tokens = dict(FALLBACK, **theme["tokens"])
        _dark = bool(theme.get("dark", False))
    t = _tokens
    bad_bg = "#4A1C1C" if _dark else "#FFC7CE"
    bad_fg = "#FFCDD2" if _dark else "#9C0006"
    app.setStyleSheet(f"""
QWidget {{ color: {t['text']}; }}
QWidget#Page, QDialog {{ background: {t['bg']}; }}
QFrame#Card {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 10px; }}
QGroupBox {{
    background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px;
    margin-top: 10px; padding-top: 10px; font-weight: 600;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; color: {t['muted']}; }}
QLabel[role="title"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="cardTitle"] {{ font-weight: 600; font-size: 13px; }}
QLabel[role="muted"] {{ color: {t['muted']}; }}
QLabel[role="mono"] {{ font-family: monospace; }}
QLabel[role="pill"] {{
    border: 1px solid {t['border']}; border-radius: 9px; padding: 2px 9px; color: {t['muted']};
    font-size: 11px; font-weight: 600;
}}
QLabel[role="pill"][state="ok"] {{ color: {t['success']}; border-color: {t['success']}; }}
QLabel[role="pill"][state="err"] {{ color: {t['danger']}; border-color: {t['danger']}; }}
QLabel[role="pill"][state="warn"] {{ color: {t['warning']}; border-color: {t['warning']}; }}
QLabel[role="pill"][state="accent"] {{ color: {t['accent']}; border-color: {t['accent']}; }}
QPushButton, QToolButton {{
    background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 4px 10px;
}}
QPushButton:hover, QToolButton:hover {{ background: {t['hover']}; }}
QPushButton:disabled, QToolButton:disabled {{ color: {t['muted']}; }}
QPushButton[variant="primary"] {{
    background: {t['primary']}; color: {t['accent_text']}; border-color: {t['primary']}; font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{ background: {t['primary_hover']}; }}
QPushButton[variant="primary"]:disabled {{ background: {t['border']}; border-color: {t['border']}; color: {t['muted']}; }}
QPushButton[variant="danger"] {{
    color: {t['danger']}; border-color: {t['danger']};
}}
QLineEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
    background: {t['input']}; border: 1px solid {t['border']};
    border-radius: 6px; padding: 3px 6px; selection-background-color: {t['selection']}; selection-color: {t['text']};
}}
QLineEdit[bad="true"] {{ background: {bad_bg}; color: {bad_fg}; border-color: {t['danger']}; }}
QComboBox {{
    background: {t['input']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 3px 8px;
}}
QComboBox QAbstractItemView {{ background: {t['surface']}; selection-background-color: {t['selection']}; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; padding: 6px 14px; color: {t['muted']}; border: none; }}
QTabBar::tab:selected {{ color: {t['accent']}; border-bottom: 2px solid {t['accent']}; font-weight: 600; }}
QTableWidget, QTableView {{
    background: {t['row']}; alternate-background-color: {t['row_alt']}; border: 1px solid {t['border']};
    border-radius: 6px; gridline-color: {t['border']}; selection-background-color: {t['selection']};
    selection-color: {t['text']};
}}
QHeaderView::section {{
    background: {t['surface2']}; border: none; border-right: 1px solid {t['border']};
    border-bottom: 1px solid {t['border']}; padding: 4px 6px; color: {t['muted']}; font-weight: 600;
}}
QProgressBar {{
    background: {t['surface2']}; border: 1px solid {t['border']}; border-radius: 5px;
    text-align: center; height: 14px; font-size: 11px;
}}
QProgressBar::chunk {{ background: {t['accent']}; border-radius: 4px; }}
QCheckBox, QRadioButton {{ spacing: 6px; }}
""")


def repolish(w):
    w.style().unpolish(w)
    w.style().polish(w)


def label(text: str = "", role: str | None = None, wrap: bool = False) -> QLabel:
    w = QLabel(text)
    if role:
        w.setProperty("role", role)
    w.setWordWrap(wrap)
    return w


def button(text: str, variant: str | None = None, slot=None, tip: str | None = None) -> QPushButton:
    b = QPushButton(text)
    if variant:
        b.setProperty("variant", variant)
    if slot:
        b.clicked.connect(slot)
    if tip:
        b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class Card(QFrame):
    def __init__(self, title: str | None = None, subtitle: str | None = None, margins: int = 12, spacing: int = 8):
        super().__init__()
        self.setObjectName("Card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(margins, margins, margins, margins)
        self.lay.setSpacing(spacing)
        if title:
            self.lay.addWidget(label(title, "cardTitle"))
            if subtitle:
                self.lay.addWidget(label(subtitle, "muted", wrap=True))


class Pill(QLabel):
    def __init__(self, text: str = "", state: str = ""):
        super().__init__(text)
        self.setProperty("role", "pill")
        self.set(text, state)

    def set(self, text: str, state: str = ""):
        self.setText(text)
        self.setProperty("state", state)
        self.setVisible(bool(text))
        repolish(self)


def confirm(parent, title: str, text: str, ok_text: str = "Evet", cancel_text: str = "İptal") -> bool:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(text)
    yes = box.addButton(ok_text, QMessageBox.ButtonRole.AcceptRole)
    box.addButton(cancel_text, QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is yes


def bold(f: QFont) -> QFont:
    f.setBold(True)
    return f
