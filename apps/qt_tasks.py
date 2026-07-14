"""RTOS Tasks pane — heap summary + task list from 'tasks list'."""

import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_table import HTable, QTableWidgetItem

from qt_spinbox import HSpinBox

_COLUMNS = ["Task Name", "State", "Priority", "Stack (B)", "#"]

_STATE_LABEL = {
    "X": "Executing",
    "R": "Ready",
    "B": "Blocked",
    "D": "Delayed",
    "S": "Suspended",
}

_STATE_COLOR = {
    "X": "#d4edda",
    "R": "#cce5ff",
    "B": "#fff3cd",
    "D": "#ffeeba",
    "S": "#f8d7da",
}

_RE_HEAP = re.compile(
    r"Heap:\s*([\d]+)\s*bytes.*?free:\s*([\d]+)\s*bytes\s*\(([\d]+)\s*contiguous.*?frag:\s*([\d.]+)%\)",
    re.IGNORECASE,
)
_RE_TASK = re.compile(r"^(\S+)\s+([XRBDS])\s+(\d+)\s+(\d+)\s+(\d+)\s*$")


class TasksWindow(QWidget):
    """Shows RTOS task list and heap info; refreshes on demand or on a timer."""

    def __init__(self, serial_terminal, parser=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("RTOS Tasks")
        self.setWindowFlag(Qt.WindowType.Window)
        self._st     = serial_terminal
        self._parser = parser
        self._timer  = QTimer(self)
        self._timer.timeout.connect(self._refresh)

        self._build_ui()
        serial_terminal.register_connection_state_callback(self._on_connection_changed)
        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ── Toolbar ───────────────────────────────────────────────────
        bar = QHBoxLayout()

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._refresh)
        bar.addWidget(self._refresh_btn)

        self._auto_cb = QCheckBox("Auto")
        self._auto_cb.toggled.connect(self._on_auto_toggled)
        bar.addWidget(self._auto_cb)

        self._interval_spin = HSpinBox()
        self._interval_spin.setRange(500, 60_000)
        self._interval_spin.setValue(2_000)
        self._interval_spin.setSingleStep(500)
        self._interval_spin.setSuffix(" ms")
        self._interval_spin.valueChanged.connect(self._on_interval_changed)
        bar.addWidget(self._interval_spin)

        bar.addStretch()
        root.addLayout(bar)

        # ── Heap summary ──────────────────────────────────────────────
        heap_box = QGroupBox("Heap")
        heap_row = QHBoxLayout(heap_box)
        self._heap_used_lbl  = QLabel("—")
        self._heap_free_lbl  = QLabel("—")
        self._heap_contig_lbl = QLabel("—")
        self._heap_frag_lbl  = QLabel("—")
        for caption, lbl in [
            ("Used:", self._heap_used_lbl),
            ("Free:", self._heap_free_lbl),
            ("Largest block:", self._heap_contig_lbl),
            ("Frag:", self._heap_frag_lbl),
        ]:
            heap_row.addWidget(QLabel(caption))
            heap_row.addWidget(lbl)
            heap_row.addSpacing(12)
        heap_row.addStretch()
        root.addWidget(heap_box)

        # ── Task table ────────────────────────────────────────────────
        self._table = HTable(0, len(_COLUMNS))
        self._table.setHorizontalHeaderLabels(_COLUMNS)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in range(1, len(_COLUMNS)):
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
        root.addWidget(self._table)

        # ── Legend ────────────────────────────────────────────────────
        legend_row = QHBoxLayout()
        for code, label in _STATE_LABEL.items():
            dot = QLabel("■")
            dot.setStyleSheet(f"color: {_STATE_COLOR[code]};")
            legend_row.addWidget(dot)
            legend_row.addWidget(QLabel(f"{code}={label}"))
            legend_row.addSpacing(6)
        legend_row.addStretch()
        root.addLayout(legend_row)

        self.adjustSize()

    # ------------------------------------------------------------------
    def _send(self, cmd: str, callback) -> None:
        if self._parser is not None:
            self._parser.send(cmd, callback)
        elif self._st.serial.is_connected():
            self._st.send_command(cmd + "\n")

    def _refresh(self) -> None:
        if not self._st.serial.is_connected():
            return
        self._refresh_btn.setEnabled(False)
        self._send("tasks list", self._on_response)

    def _on_response(self, lines: list, status: str) -> None:
        self._refresh_btn.setEnabled(True)
        if status != "OK":
            return

        tasks = []
        heap_matched = False

        for line in lines:
            if not heap_matched:
                m = _RE_HEAP.search(line)
                if m:
                    used, free, contig, frag = m.groups()
                    total = int(used) + int(free)
                    pct   = f"{int(used) / total * 100:.1f}%" if total else "—"
                    self._heap_used_lbl.setText(f"{int(used):,} B ({pct})")
                    self._heap_free_lbl.setText(f"{int(free):,} B")
                    self._heap_contig_lbl.setText(f"{int(contig):,} B")
                    self._heap_frag_lbl.setText(f"{frag}%")
                    heap_matched = True
                    continue

            m = _RE_TASK.match(line.strip())
            if m:
                name, state, prio, stack, num = m.groups()
                tasks.append((name, state, prio, stack, num))

        self._table.setRowCount(len(tasks))
        for row, (name, state, prio, stack, num) in enumerate(tasks):
            color = _STATE_COLOR.get(state, "#ffffff")
            full  = _STATE_LABEL.get(state, state)
            items = [name, full, prio, stack, num]
            for col, text in enumerate(items):
                item = QTableWidgetItem(text)
                if col == 1:
                    item.setBackground(QColor(color))
                item.setTextAlignment(
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter if col == 0
                    else Qt.AlignmentFlag.AlignCenter
                )
                self._table.setItem(row, col, item)

    # ------------------------------------------------------------------
    def _on_auto_toggled(self, on: bool) -> None:
        if on:
            self._timer.start(self._interval_spin.value())
            self._refresh()
        else:
            self._timer.stop()

    def _on_interval_changed(self, ms: int) -> None:
        if self._timer.isActive():
            self._timer.setInterval(ms)

    def _on_connection_changed(self) -> None:
        connected = self._st.serial.is_connected()
        self._refresh_btn.setEnabled(connected)
        self._auto_cb.setEnabled(connected)
        if not connected:
            self._timer.stop()
            self._auto_cb.setChecked(False)
