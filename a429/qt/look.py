"""AXIL Studio tema uyumu ve ortak Qt widget yardımcıları."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPainterPath, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QStyleFactory, QVBoxLayout,
)

FALLBACK = {
    "bg": "#F2F4F8", "surface": "#FFFFFF", "surface2": "#EEF1F7", "border": "#D3DAE6", "text": "#1A1A1A",
    "muted": "#5A6475", "accent": "#003087", "accent_text": "#FFFFFF", "accent_soft": "#E5EAF3",
    "primary": "#003087", "primary_hover": "#33599F", "hover": "#E6EAF2", "selection": "#CCD6E7",
    "danger": "#C62828", "success": "#2E7D32", "warning": "#F7931D", "input": "#FFFFFF",
    "row": "#F6F7FA", "row_alt": "#ECEFF5",
}
_tokens = dict(FALLBACK)
_dark = False
_style_set = False


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


def _build_palette(t: dict) -> QPalette:
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(t["bg"]))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Base, QColor(t["input"]))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(t["row_alt"]))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(t["surface"]))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Text, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Button, QColor(t["surface"]))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.Highlight, QColor(t["selection"]))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(t["text"]))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(t["muted"]))
    return pal


def apply(app, theme: dict | None = None):
    """AXIL Studio tema paketini ({"dark": bool, "tokens": {...}}) uygular (Fusion stili)."""
    global _tokens, _dark, _style_set
    if not _style_set:
        fusion = QStyleFactory.create("Fusion")
        if fusion is not None:
            app.setStyle(fusion)
        _style_set = True

    if theme and theme.get("tokens"):
        _tokens = dict(FALLBACK, **theme["tokens"])
        _dark = bool(theme.get("dark", False))
    t = _tokens
    app.setPalette(_build_palette(t))

    bad_bg = "#4A1C1C" if _dark else "#FFC7CE"
    bad_fg = "#FFCDD2" if _dark else "#9C0006"
    app.setStyleSheet(f"""
QWidget {{ color: {t['text']}; }}
QWidget#Page, QDialog {{ background: {t['bg']}; }}
QFrame#Card {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 10px; }}
QFrame#SubCard {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; }}
QFrame#SubPanel {{ background: {t['bg']}; border: 1px solid {t['border']}; border-radius: 8px; }}
QFrame#StatBox {{ background: {t['bg']}; border: 1px solid {t['border']}; border-radius: 8px; }}

QGroupBox {{
    background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px;
    margin-top: 12px; padding: 10px 8px 8px 8px; font-weight: 600;
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 10px; padding: 0 6px; color: {t['muted']}; background: {t['surface']};
}}

QLabel[role="title"] {{ font-size: 15px; font-weight: 600; }}
QLabel[role="cardTitle"] {{ font-weight: 600; font-size: 13px; }}
QLabel[role="muted"] {{ color: {t['muted']}; }}
QLabel[role="mono"] {{ font-family: monospace; }}
QLabel[role="pill"] {{
    border: 1px solid {t['border']}; border-radius: 9px; padding: 2px 9px; color: {t['muted']};
    font-size: 11px; font-weight: 600; background: {t['surface']};
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
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{
    border-color: {t['accent']};
}}
QLineEdit[bad="true"] {{ background: {bad_bg}; color: {bad_fg}; border-color: {t['danger']}; }}
QComboBox {{
    background: {t['input']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 3px 8px;
}}
QComboBox QAbstractItemView {{
    background: {t['surface']}; border: 1px solid {t['border']};
    selection-background-color: {t['selection']}; selection-color: {t['text']};
}}

QTabWidget::pane {{
    border: none; border-top: 1px solid {t['border']};
    background: transparent; top: -1px;
}}
QTabWidget::tab-bar {{ left: 6px; }}
QTabWidget QStackedWidget > QWidget {{ background: transparent; }}
QTabBar {{ background: transparent; qproperty-drawBase: 0; }}
QTabBar::tab {{
    background: transparent; color: {t['muted']};
    padding: 8px 16px; margin-right: 2px;
    border: none; border-bottom: 2px solid transparent;
    font-weight: 500;
}}
QTabBar::tab:hover {{
    color: {t['text']}; background: {t['hover']};
    border-top-left-radius: 6px; border-top-right-radius: 6px;
}}
QTabBar::tab:selected {{
    color: {t['accent']}; border-bottom: 2px solid {t['accent']};
    font-weight: 600; background: transparent;
}}

QTableWidget, QTableView {{
    background: {t['row']}; alternate-background-color: {t['row_alt']}; border: 1px solid {t['border']};
    border-radius: 6px; gridline-color: {t['border']}; selection-background-color: {t['selection']};
    selection-color: {t['text']};
}}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{
    background: {t['surface2']}; border: none; border-right: 1px solid {t['border']};
    border-bottom: 1px solid {t['border']}; padding: 5px 8px;
    color: {t['muted']}; font-size: 11px; font-weight: 600;
}}
QTableCornerButton::section {{ background: {t['surface2']}; border: none; }}

QSplitter::handle {{ background: transparent; }}
QSplitter::handle:horizontal {{ width: 8px; }}
QSplitter::handle:vertical {{ height: 8px; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle {{ background: {t['border']}; border-radius: 3px; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {t['muted']}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QMenu {{ background: {t['surface']}; border: 1px solid {t['border']}; border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 22px 6px 14px; border-radius: 5px; }}
QMenu::item:selected {{ background: {t['selection']}; color: {t['text']}; }}
QMenu::separator {{ height: 1px; background: {t['border']}; margin: 4px 6px; }}

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


def pencil_icon(col: QColor | None = None, size: int = 15) -> QIcon:
    """AXIL Studio üslubunda keskin (2x HiDPI) kalem ikonu üretir."""
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 24.0
    pen = QPen(col or color("muted"), 2.0 * s, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    path = QPainterPath()
    path.moveTo(4 * s, 20 * s)
    path.lineTo(5 * s, 16 * s)
    path.lineTo(16.5 * s, 4.5 * s)
    path.lineTo(19.5 * s, 7.5 * s)
    path.lineTo(8 * s, 19 * s)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(14 * s, 7 * s), QPointF(17 * s, 10 * s))
    p.end()
    return QIcon(pm)


def edit_button(slot, tip: str = "Düzenle…") -> QPushButton:
    """Kompakt kalem ikonlu düzenle düğmesi."""
    b = QPushButton()
    b.setIcon(pencil_icon())
    b.setIconSize(QSize(15, 15))
    b.setFixedSize(28, 26)
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setStyleSheet("QPushButton { padding: 0px; }")
    if slot:
        b.clicked.connect(slot)
    return b


class Card(QFrame):
    def __init__(self, title: str | None = None, subtitle: str | None = None, margins: int = 12, spacing: int = 8, object_name: str = "Card"):
        super().__init__()
        self.setObjectName(object_name)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(margins, margins, margins, margins)
        self.lay.setSpacing(spacing)
        if title:
            self.lay.addWidget(label(title, "cardTitle"))
            if subtitle:
                self.lay.addWidget(label(subtitle, "muted", wrap=True))


def wrap_tabs(tabs, object_name: str = "SubCard") -> Card:
    """QTabWidget'ı sekme başlığıyla birlikte tek bir dış çerçeve (outline) içine alır."""
    card = Card(margins=1, spacing=0, object_name=object_name)
    card.lay.addWidget(tabs)
    return card


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
