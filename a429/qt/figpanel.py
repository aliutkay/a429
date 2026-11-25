"""matplotlib Qt figür paneli (fareyle zoom/kaydırma) ve tek grafik penceresi."""
from __future__ import annotations

import sys

import matplotlib
matplotlib.use("QtAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg, NavigationToolbar2QT

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QVBoxLayout, QWidget

from ..charts import draw_examples, draw_single, relayout

TIME_UNITS = ["clk", "ns", "µs", "ms"]


class _Toolbar(NavigationToolbar2QT):
    def __init__(self, canvas, parent, panel):
        self._panel = panel
        super().__init__(canvas, parent)

    def home(self, *args):
        self._panel.reset()


class FigPanel(QWidget):
    """matplotlib figürü + fare ile yakınlaştırma / kaydırma."""

    HELP = "Tekerlek / iki parmak: yakınlaştır · Ctrl+Tekerlek: yalnız dikey · Sürükle: kaydır · Çift tık: görünümü sıfırla"
    ZOOM_STEP = 1.08 if sys.platform == "darwin" else 1.3

    def __init__(self, parent=None, figsize=(12, 6)):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.fig = Figure(figsize=figsize, dpi=90)
        self.canvas = FigureCanvasQTAgg(self.fig)
        lay.addWidget(self.canvas, 1)

        bar = QHBoxLayout()
        bar.setContentsMargins(4, 0, 4, 2)
        self.tb = _Toolbar(self.canvas, self, self)
        bar.addWidget(self.tb)
        lbl = QLabel(self.HELP)
        lbl.setProperty("role", "muted")
        bar.addWidget(lbl)
        bar.addStretch(1)
        lay.addLayout(bar)

        self._drag = None
        c = self.canvas
        c.mpl_connect("scroll_event", self._on_scroll)
        c.mpl_connect("button_press_event", self._on_press)
        c.mpl_connect("button_release_event", lambda e: setattr(self, "_drag", None))
        c.mpl_connect("motion_notify_event", self._on_move)
        c.mpl_connect("resize_event", lambda e: (relayout(self.fig), self.canvas.draw_idle()))

    def draw(self):
        relayout(self.fig)
        self.canvas.draw_idle()

    def reset(self):
        for ax, (xl, yl) in getattr(self.fig, "_home", {}).items():
            ax.set_xlim(xl)
            ax.set_ylim(yl)
        self.draw()

    @staticmethod
    def _key(ev, name: str) -> bool:
        return name in (ev.key or "").lower()

    def _on_scroll(self, ev):
        ax = ev.inaxes
        if ax is None or ev.xdata is None:
            return
        f = 1 / self.ZOOM_STEP if ev.button == "up" else self.ZOOM_STEP
        if self._key(ev, "shift"):
            x0, x1 = ax.get_xlim()
            d = (x1 - x0) * 0.15 * (-1 if ev.button == "up" else 1)
            ax.set_xlim(x0 + d, x1 + d)
        elif self._key(ev, "control") or self._key(ev, "ctrl"):
            y0, y1 = ax.get_ylim()
            y = ev.ydata
            ax.set_ylim(y - (y - y0) * f, y + (y1 - y) * f)
        else:
            x0, x1 = ax.get_xlim()
            y0, y1 = ax.get_ylim()
            x, y = ev.xdata, ev.ydata
            ax.set_xlim(x - (x - x0) * f, x + (x1 - x) * f)
            ax.set_ylim(y - (y - y0) * f, y + (y1 - y) * f)
        self.draw()

    def _on_press(self, ev):
        if ev.inaxes is None or self.tb.mode:
            return
        if ev.dblclick:
            self.reset()
            return
        if ev.button == 1:
            self._drag = (ev.inaxes, ev.x, ev.y, ev.inaxes.get_xlim(), ev.inaxes.get_ylim())

    def _on_move(self, ev):
        if not self._drag or self.tb.mode:
            return
        ax, px0, py0, (x0, x1), (y0, y1) = self._drag
        dx = (ev.x - px0) / (ax.bbox.width or 1) * (x1 - x0)
        dy = (ev.y - py0) / (ax.bbox.height or 1) * (y1 - y0)
        ax.set_xlim(x0 - dx, x1 - dx)
        ax.set_ylim(y0 - dy, y1 - dy)
        self.draw()


class ChartWindow(QDialog):
    """Tek bir RX Config grafiğini ayrı pencerede gösterir."""

    def __init__(self, app, kind: str, case: str):
        super().__init__(app)
        self.app, self.kind, self.case = app, kind, case
        self.setWindowTitle(f"RX {'Örnek dalga formu' if kind == 'example' else 'Tek Bit analizi'} – {case}")
        self.resize(1160, 620)
        lay = QVBoxLayout(self)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Birim:"))
        self.unit_cb = QComboBox()
        self.unit_cb.addItems(TIME_UNITS)
        self.unit_cb.currentTextChanged.connect(lambda _: self.draw())
        bar.addWidget(self.unit_cb)

        self.pat_edit = None
        if kind == "example":
            bar.addSpacing(12)
            bar.addWidget(QLabel("Bit deseni (1/0):"))
            self.pat_edit = QLineEdit("10110010")
            self.pat_edit.setFixedWidth(160)
            self.pat_edit.textChanged.connect(lambda _: self.draw())
            bar.addWidget(self.pat_edit)
        bar.addStretch(1)
        lay.addLayout(bar)

        self.panel = FigPanel(self, (12, 6))
        lay.addWidget(self.panel, 1)
        self.draw()

    def draw(self):
        app = self.app
        if not app.res:
            return
        try:
            unit = self.unit_cb.currentText()
            if self.kind == "example":
                txt = self.pat_edit.text() if self.pat_edit else "10110010"
                pat = [1 if c == "1" else 0 for c in txt if c in "01"] or [1, 0]
                draw_examples(self.panel.fig, app.res, app.ci.clk_mhz, unit, pat[:16], only=self.case)
            else:
                draw_single(self.panel.fig, app.res, app.ci.clk_mhz, unit, self.case)
            self.panel.draw()
        except Exception as e:
            app.set_status(f"Grafik hatası: {e}")
