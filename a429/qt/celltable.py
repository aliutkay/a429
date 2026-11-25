"""Hücre bazında PASS/FAIL renklendirme yapan Qt tablo bileşeni (QTableView + QAbstractTableModel)."""
from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import QAbstractItemView, QHeaderView, QTableView, QToolTip

from . import look

LIGHT_PASS_BG, LIGHT_PASS_FG = QColor("#C6EFCE"), QColor("#006100")
LIGHT_FAIL_BG, LIGHT_FAIL_FG = QColor("#FFC7CE"), QColor("#9C0006")
DARK_PASS_BG, DARK_PASS_FG = QColor("#1E3A24"), QColor("#A5D6A7")
DARK_FAIL_BG, DARK_FAIL_FG = QColor("#4A1C1C"), QColor("#EF9A9A")


class Cell:
    """ok: True (PASS), False (FAIL), None (kontrol yok). why: neden açıklaması."""
    __slots__ = ("text", "ok", "why")

    def __init__(self, text, ok=None, why: str = ""):
        self.text = "" if text is None else str(text)
        self.ok = ok
        self.why = why

    def tip(self) -> str:
        if self.ok is None:
            return self.why
        return f"{'PASS' if self.ok else 'FAIL'}: {self.why}"


class _CellModel(QAbstractTableModel):
    def __init__(self, columns: list[str], parent=None):
        super().__init__(parent)
        self.columns = list(columns)
        self.rows: list[list[Cell]] = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = [[c if isinstance(c, Cell) else Cell(c) for c in r] for r in rows]
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.columns)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.columns[section]
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        r, c = index.row(), index.column()
        if r >= len(self.rows) or c >= len(self.rows[r]):
            return None
        cell = self.rows[r][c]
        if role == Qt.ItemDataRole.DisplayRole:
            return cell.text
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            return cell.tip() or None
        if role == Qt.ItemDataRole.BackgroundRole and cell.ok is not None:
            if look.is_dark():
                return QBrush(DARK_PASS_BG if cell.ok else DARK_FAIL_BG)
            return QBrush(LIGHT_PASS_BG if cell.ok else LIGHT_FAIL_BG)
        if role == Qt.ItemDataRole.ForegroundRole and cell.ok is not None:
            if look.is_dark():
                return QBrush(DARK_PASS_FG if cell.ok else DARK_FAIL_FG)
            return QBrush(LIGHT_PASS_FG if cell.ok else LIGHT_FAIL_FG)
        return None


class CellTable(QTableView):
    def __init__(self, columns: list[str], widths: list[int], on_double=None, parent=None):
        super().__init__(parent)
        self._model = _CellModel(columns, self)
        self.setModel(self._model)
        self.on_double = on_double

        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(22)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        self.horizontalHeader().setStretchLastSection(False)
        for i, w in enumerate(widths):
            self.setColumnWidth(i, w)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_reason)
        if on_double:
            self.doubleClicked.connect(lambda idx: self.on_double(idx.row()))

    def set_rows(self, rows):
        self._model.set_rows(rows)

    def cell_text(self, row: int, col: int) -> str:
        return self._model.rows[row][col].text

    def _show_reason(self, pos):
        idx = self.indexAt(pos)
        if not idx.isValid():
            return
        tip = self._model.data(idx, Qt.ItemDataRole.ToolTipRole)
        if tip:
            QToolTip.showText(self.viewport().mapToGlobal(pos), tip, self)
