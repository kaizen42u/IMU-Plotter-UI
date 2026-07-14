"""Event management pane — list, enable, disable firmware events."""

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from qt_table import HTable, QTableWidgetItem

_RE_EVENT = re.compile(r"^(0x[0-9a-fA-F]+)\s+(\(enabled\))?\s*(\S+)")

_COL_ID     = 0
_COL_NAME   = 1
_COL_ACTION = 2
_COLS = ["ID", "Name", ""]


class EventWindow(QWidget):
    """List all firmware events; toggle each one with an inline button."""

    def __init__(self, serial_terminal, parser=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Events")
        self.setWindowFlag(Qt.WindowType.Window)
        self._st     = serial_terminal
        self._parser = parser

        self._build_ui()
        serial_terminal.register_connection_state_callback(self._on_connection_changed)
        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        bar = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.clicked.connect(self._do_list)
        bar.addWidget(self._refresh_btn)
        bar.addStretch()
        root.addLayout(bar)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self._status_lbl)

        self._table = HTable(0, len(_COLS))
        self._table.setHorizontalHeaderLabels(_COLS)
        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_ID,     QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(_COL_NAME,   QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(_COL_ACTION, QHeaderView.ResizeMode.Fixed)
        hdr.resizeSection(_COL_ACTION, 80)
        root.addWidget(self._table)

        self.setMinimumWidth(420)
        self.adjustSize()

    # ------------------------------------------------------------------
    def _send(self, cmd: str, callback=None) -> None:
        if self._parser is not None:
            self._parser.send(cmd, callback)
        elif self._st.serial.is_connected():
            self._st.send_command(cmd + "\n")

    # ------------------------------------------------------------------
    def _do_list(self) -> None:
        self._refresh_btn.setEnabled(False)
        def on_resp(lines, status):
            self._refresh_btn.setEnabled(True)
            if status != "OK":
                self._status_lbl.setText("List failed.")
                return
            events = []
            for line in lines:
                m = _RE_EVENT.match(line.strip())
                if m:
                    eid, enabled_tag, name = m.groups()
                    events.append((eid, name, bool(enabled_tag)))
            self._populate(events)
            enabled_count = sum(1 for _, _, e in events if e)
            self._status_lbl.setText(
                f"{len(events)} event(s) — {enabled_count} enabled"
            )
        self._send("event list", on_resp)

    def _populate(self, events: list[tuple[str, str, bool]]) -> None:
        self._table.setRowCount(len(events))
        for row, (eid, name, enabled) in enumerate(events):
            id_item = QTableWidgetItem(eid)
            id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self._table.setItem(row, _COL_ID, id_item)

            name_item = QTableWidgetItem(name)
            name_item.setTextAlignment(
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            )
            if enabled:
                name_item.setForeground(
                    self._table.palette().color(self._table.foregroundRole())
                )
            else:
                name_item.setForeground(Qt.GlobalColor.gray)
            self._table.setItem(row, _COL_NAME, name_item)

            btn = QPushButton("Disable" if enabled else "Enable")
            btn.setFixedHeight(22)
            if enabled:
                btn.setStyleSheet("font-size: 9pt; color: #721c24; background: #f8d7da;")
            else:
                btn.setStyleSheet("font-size: 9pt; color: #155724; background: #d4edda;")
            btn.clicked.connect(lambda _, e=eid, on=enabled: self._toggle(e, on))
            self._table.setCellWidget(row, _COL_ACTION, btn)

        self._table.resizeRowsToContents()

    def _toggle(self, eid: str, currently_enabled: bool) -> None:
        verb = "disable" if currently_enabled else "enable"
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(f"{verb} {eid}: {msg}")
            self._do_list()
        self._send(f"event {verb} {eid}", on_resp)

    # ------------------------------------------------------------------
    def _on_connection_changed(self) -> None:
        connected = self._st.serial.is_connected()
        self._refresh_btn.setEnabled(connected)
        if not connected:
            self._table.setRowCount(0)
            self._status_lbl.setText("")
