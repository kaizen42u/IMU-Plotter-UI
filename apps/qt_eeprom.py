"""EEPROM peripheral pane."""

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtCore import QRegularExpression
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


_ESP_LOG_RE = re.compile(r"^[IWEDEV] \(\d+\)")

def _is_esp_log(line: str) -> bool:
    """True for ESP-IDF log lines like 'I (12345) tag: message | file.c:N'."""
    return bool(_ESP_LOG_RE.match(line))


class EEPROMWindow(QWidget):
    """EEPROM peripheral control pane."""

    def __init__(self, serial_terminal, parser=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("EEPROM")
        self.setWindowFlag(Qt.WindowType.Window)
        self.setMinimumWidth(380)
        self._st = serial_terminal
        self._parser = parser
        self._build_ui()
        serial_terminal.register_connection_state_callback(self._on_connection_changed)
        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Keys list ─────────────────────────────────────────────────
        keys_box = QGroupBox("Keys in namespace")
        keys_layout = QVBoxLayout(keys_box)
        keys_layout.setContentsMargins(6, 4, 6, 6)
        keys_layout.setSpacing(4)

        self._refresh_btn = QPushButton("Refresh")
        self._refresh_btn.setFixedWidth(64)
        self._refresh_btn.clicked.connect(self._do_keys)
        refresh_row = QHBoxLayout()
        refresh_row.addStretch()
        refresh_row.addWidget(self._refresh_btn)
        keys_layout.addLayout(refresh_row)

        self._keys_list = QListWidget()
        self._keys_list.setMaximumHeight(100)
        self._keys_list.itemClicked.connect(self._on_key_selected)
        keys_layout.addWidget(self._keys_list)

        add_row = QHBoxLayout()
        self._new_key_edit = QLineEdit()
        self._new_key_edit.setPlaceholderText("new key name…")
        self._new_key_edit.setValidator(QRegularExpressionValidator(QRegularExpression(r"\S*")))
        self._new_key_edit.returnPressed.connect(self._do_set_key)
        add_row.addWidget(self._new_key_edit, stretch=1)
        self._set_btn = QPushButton("Add")
        self._set_btn.setFixedWidth(40)
        self._set_btn.clicked.connect(self._do_set_key)
        add_row.addWidget(self._set_btn)
        keys_layout.addLayout(add_row)

        root.addWidget(keys_box)

        # ── Value display ─────────────────────────────────────────────
        val_box = QGroupBox("Value")
        val_layout = QVBoxLayout(val_box)
        val_layout.setContentsMargins(6, 4, 6, 6)
        self._value_display = QTextEdit()
        self._value_display.setReadOnly(True)
        self._value_display.setMaximumHeight(70)
        self._value_display.setPlaceholderText("(read to show)")
        val_layout.addWidget(self._value_display)
        root.addWidget(val_box)

        # ── Write data row ────────────────────────────────────────────
        data_row = QHBoxLayout()
        data_row.addWidget(QLabel("Data:"))
        self._data_edit = QLineEdit()
        self._data_edit.setPlaceholderText("string to write")
        self._data_edit.returnPressed.connect(self._do_write)
        data_row.addWidget(self._data_edit, stretch=1)
        root.addLayout(data_row)

        # ── Action buttons ────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._init_btn  = QPushButton("Init")
        self._read_btn  = QPushButton("Read")
        self._write_btn = QPushButton("Write")
        self._clear_btn = QPushButton("Clear")
        for btn in (self._init_btn, self._read_btn, self._write_btn, self._clear_btn):
            btn_row.addWidget(btn)
        root.addLayout(btn_row)

        erase_row = QHBoxLayout()
        erase_row.addStretch()
        self._erase_btn = QPushButton("Erase NVS ⚠")
        self._erase_btn.setStyleSheet("color: #c0392b; font-weight: bold;")
        self._erase_btn.setToolTip("eeprom erase — destructive, erases entire NVS partition")
        erase_row.addWidget(self._erase_btn)
        root.addLayout(erase_row)

        # Status line
        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self._status_lbl)

        # Button connections
        self._init_btn.clicked.connect(self._do_init)
        self._read_btn.clicked.connect(self._do_read)
        self._write_btn.clicked.connect(self._do_write)
        self._clear_btn.clicked.connect(self._do_clear)
        self._erase_btn.clicked.connect(self._do_erase)

        self._all_btns = (
            self._init_btn, self._refresh_btn, self._read_btn,
            self._write_btn, self._clear_btn, self._erase_btn,
            self._set_btn,
        )
        self._new_key_edit.setEnabled(False)

    # ------------------------------------------------------------------
    # Helpers

    def _send(self, cmd: str, callback=None) -> None:
        if self._parser is not None:
            self._parser.send(cmd, callback)
        elif self._st.serial.is_connected():
            self._st.send_command(cmd + "\n")

    def _set_status(self, text: str) -> None:
        self._status_lbl.setText(text)

    # ------------------------------------------------------------------
    # Button handlers

    def _do_init(self) -> None:
        self._send("eeprom init", self._on_simple_response)

    def _do_keys(self) -> None:
        self._send("eeprom keys", self._on_keys_response)

    def _on_key_selected(self, item) -> None:
        key = item.data(Qt.ItemDataRole.UserRole) or ""
        if not key:
            return
        self._value_display.clear()
        self._send(f"eeprom key {key}",
                   lambda lines, st: st == "OK" and self._send("eeprom read", self._on_read_response))

    def _do_set_key(self) -> None:
        key = self._new_key_edit.text().strip()
        if not key:
            return
        self._new_key_edit.clear()
        self._value_display.clear()
        self._set_status(f"Creating key '{key}'…")
        self._send(f"eeprom key {key}", lambda lines, st:
            self._send("eeprom write _", lambda lines2, st2:
                self._send("eeprom clear", lambda lines3, st3: (
                    self._set_status(f"Key '{key}' created." if st3 == "OK" else "Create failed."),
                    self._do_keys() if st3 == "OK" else None,
                )) if st2 == "OK" else self._set_status("Create failed (write).")
            ) if st == "OK" else self._set_status("Create failed (key).")
        )

    def _do_read(self) -> None:
        self._send("eeprom read", self._on_read_response)

    def _do_write(self) -> None:
        data = self._data_edit.text().strip()
        if not data:
            return
        self._send(f"eeprom write {data}", self._on_write_response)

    def _do_clear(self) -> None:
        self._value_display.clear()
        self._send("eeprom clear", self._on_simple_response)

    def _do_erase(self) -> None:
        reply = QMessageBox.warning(
            self, "Erase NVS",
            "This will erase the entire NVS partition.\nThis cannot be undone.",
            QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Ok:
            self._value_display.clear()
            self._send("eeprom erase", self._on_simple_response)

    # ------------------------------------------------------------------
    # Response parsers

    def _on_simple_response(self, lines: list[str], status: str) -> None:
        """Show the first non-log firmware line as status."""
        for line in lines:
            s = line.strip()
            if s and not _is_esp_log(s):
                self._set_status(s)
                return
        self._set_status("OK" if status == "OK" else "FAIL")

    def _on_keys_response(self, lines: list[str], status: str) -> None:
        if status != "OK":
            self._set_status("Failed to list keys.")
            return
        self._keys_list.clear()
        count = 0
        for line in lines:
            s = line.strip()
            if not s:
                continue
            # Key entries are indented ("  name   type"); unindented lines are headers/messages
            m = re.match(r"(\S+)\s+(\S+)", s)
            if m and line.startswith(" "):
                key_name, key_type = m.group(1), m.group(2)
                from PySide6.QtWidgets import QListWidgetItem
                item = QListWidgetItem(f"{key_name}  ({key_type})")
                item.setData(Qt.ItemDataRole.UserRole, key_name)
                self._keys_list.addItem(item)
                count += 1
        if count == 0:
            from PySide6.QtWidgets import QListWidgetItem
            from PySide6.QtGui import QColor
            placeholder = QListWidgetItem("(no keys)")
            placeholder.setForeground(QColor("#888"))
            placeholder.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._keys_list.addItem(placeholder)
        self._set_status(f"{count} key(s) listed.")

    def _on_read_response(self, lines: list[str], status: str) -> None:
        self._value_display.clear()
        if status != "OK":
            self._value_display.setPlainText("(read failed)")
            return
        content_lines = []
        for line in lines:
            s = line.strip()
            if not s:
                continue
            if _is_esp_log(s):
                continue
            # "EEPROM is empty." — nothing to display
            if re.match(r"EEPROM is empty", s, re.IGNORECASE):
                self._set_status(s)
                continue
            content_lines.append(s)
        if content_lines:
            self._value_display.setPlainText("\n".join(content_lines))
        else:
            self._value_display.setPlainText("(empty)")

    def _on_write_response(self, lines: list[str], status: str) -> None:
        if status != "OK":
            self._set_status("Write failed.")
            return
        self._data_edit.clear()
        for line in lines:
            s = line.strip()
            if _is_esp_log(s):
                continue
            if s:
                self._set_status(s)
                break
        self._send("eeprom read", self._on_read_response)

    # ------------------------------------------------------------------
    def _on_connection_changed(self) -> None:
        connected = self._st.serial.is_connected()
        for btn in self._all_btns:
            btn.setEnabled(connected)
        self._new_key_edit.setEnabled(connected)
