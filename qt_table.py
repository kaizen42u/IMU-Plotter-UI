"""HTable — QTableWidget with sensible defaults.

Drop-in replacement for QTableWidget:
  - Vertical scrollbar always visible (reserved space, no layout shift)
  - Horizontal scrollbar as-needed
  - No edit triggers
  - Row selection
  - Alternating row colors
  - Hidden vertical header
"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem  # noqa: F401 (re-exported)


class HTable(QTableWidget):
    def __init__(self, rows: int = 0, cols: int = 0, parent=None) -> None:
        super().__init__(rows, cols, parent)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
