"""COM Port configuration window."""

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
    QCheckBox,
)

from config_store import pool


_BAUDS = ["300", "600", "1200", "2400", "4800", "9600", "14400", "19200",
          "28800", "38400", "57600", "115200", "230400", "460800", "921600"]

_BYTESIZE = {"5": 5, "6": 6, "7": 7, "8": 8}
_PARITY   = {"None": "N", "Even": "E", "Odd": "O", "Mark": "M", "Space": "S"}
_STOPBITS = {"1": 1, "1.5": 1.5, "2": 2}
_FLOWCTRL = {"None": (False, False), "RTS/CTS": (True, False), "XON/XOFF": (False, True)}

_CONNECTED_STYLE    = "color: #4EC994; font-weight: bold;"
_DISCONNECTED_STYLE = "color: #858585;"


class COMPortWindow(QWidget):
    """Stand-alone window for configuring and controlling the serial port."""

    def __init__(self, serial_terminal, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("COM Port")
        self.setWindowFlag(Qt.WindowType.Window)
        self.setMinimumWidth(340)
        self._st = serial_terminal

        # Share the "serial" section already owned by the terminal widget
        self._cfg = pool.section("serial")

        self._build_ui()
        self._refresh_ports()
        self._on_connection_changed()

        serial_terminal.register_connection_state_callback(self._on_connection_changed)

        # Poll for port list changes while window is open.
        self._port_poll = QTimer(self)
        self._port_poll.setInterval(1500)
        self._port_poll.timeout.connect(self._refresh_ports)
        self._port_poll.start()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Connection ────────────────────────────────────────────────
        conn_box = QGroupBox("Connection")
        conn_form = QFormLayout(conn_box)
        conn_form.setHorizontalSpacing(10)

        self._port_combo = QComboBox()
        self._port_combo.setEditable(True)
        self._port_combo.setMinimumWidth(160)
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(64)
        refresh_btn.clicked.connect(self._refresh_ports)
        port_row = QHBoxLayout()
        port_row.addWidget(self._port_combo, stretch=1)
        port_row.addWidget(refresh_btn)
        conn_form.addRow("Port:", port_row)

        self._baud_combo = QComboBox()
        self._baud_combo.addItems(_BAUDS)
        self._baud_combo.setCurrentText(
            self._st._baud_combo.currentText() or "921600"
        )
        self._baud_combo.setEditable(True)
        self._baud_combo.currentTextChanged.connect(self._on_baud_changed)
        conn_form.addRow("Baud rate:", self._baud_combo)

        self._status_lbl = QLabel("Disconnected")
        self._status_lbl.setStyleSheet(_DISCONNECTED_STYLE)
        conn_form.addRow("Status:", self._status_lbl)

        btn_row = QHBoxLayout()
        self._connect_btn = QPushButton("Connect")
        self._connect_btn.clicked.connect(self._do_connect)
        self._disconnect_btn = QPushButton("Disconnect")
        self._disconnect_btn.clicked.connect(self._do_disconnect)
        btn_row.addWidget(self._connect_btn)
        btn_row.addWidget(self._disconnect_btn)
        conn_form.addRow("", btn_row)

        root.addWidget(conn_box)

        # ── Serial parameters ─────────────────────────────────────────
        params_box = QGroupBox("Serial Parameters")
        params_form = QFormLayout(params_box)
        params_form.setHorizontalSpacing(10)

        self._bytesize_combo = QComboBox()
        self._bytesize_combo.addItems(list(_BYTESIZE))
        self._bytesize_combo.setCurrentText(self._cfg.bytesize or "8")
        params_form.addRow("Data bits:", self._bytesize_combo)

        self._parity_combo = QComboBox()
        self._parity_combo.addItems(list(_PARITY))
        self._parity_combo.setCurrentText(self._cfg.parity or "None")
        params_form.addRow("Parity:", self._parity_combo)

        self._stopbits_combo = QComboBox()
        self._stopbits_combo.addItems(list(_STOPBITS))
        self._stopbits_combo.setCurrentText(self._cfg.stopbits or "1")
        params_form.addRow("Stop bits:", self._stopbits_combo)

        self._flow_combo = QComboBox()
        self._flow_combo.addItems(list(_FLOWCTRL))
        self._flow_combo.setCurrentText(self._cfg.flow_control or "None")
        params_form.addRow("Flow control:", self._flow_combo)

        root.addWidget(params_box)

        # ── Startup & Reconnect ───────────────────────────────────────
        reconnect_box = QGroupBox("Startup & Reconnect")
        reconnect_lay = QVBoxLayout(reconnect_box)

        self._auto_connect_cb = QCheckBox("Auto-connect on startup")
        self._auto_connect_cb.setToolTip(
            "If the configured port is available when the app starts, connect automatically."
        )
        self._auto_connect_cb.setChecked(self._cfg.auto_connect or False)
        self._auto_connect_cb.toggled.connect(self._on_auto_connect_toggled)
        reconnect_lay.addWidget(self._auto_connect_cb)

        self._reconnect_cb = QCheckBox("Auto-reconnect on disconnect")
        reconnect_default = self._cfg.auto_reconnect or False
        self._st._reconnect_enabled = reconnect_default
        self._reconnect_cb.setChecked(reconnect_default)
        self._reconnect_cb.toggled.connect(self._on_reconnect_toggled)
        reconnect_lay.addWidget(self._reconnect_cb)

        root.addWidget(reconnect_box)

        root.addStretch()

    # ------------------------------------------------------------------
    def _refresh_ports(self) -> None:
        ports = self._st.serial.get_ports()
        current = self._port_combo.currentText()
        self._port_combo.blockSignals(True)
        self._port_combo.clear()
        self._port_combo.addItems(ports)
        if current in ports:
            self._port_combo.setCurrentText(current)
        elif ports:
            # Pre-select whatever the terminal widget has.
            st_port = self._st._port_combo.currentText()
            if st_port in ports:
                self._port_combo.setCurrentText(st_port)
        self._port_combo.blockSignals(False)

    def _do_connect(self) -> None:
        port = self._port_combo.currentText().strip()
        if not port:
            return
        try:
            baud = int(self._baud_combo.currentText())
        except ValueError:
            return

        bytesize = _BYTESIZE[self._bytesize_combo.currentText()]
        parity   = _PARITY[self._parity_combo.currentText()]
        stopbits = _STOPBITS[self._stopbits_combo.currentText()]
        rtscts, xonxoff = _FLOWCTRL[self._flow_combo.currentText()]

        self._save_config()

        self._st.connect_to(
            port, baud,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            rtscts=rtscts,
            xonxoff=xonxoff,
        )

    def _do_disconnect(self) -> None:
        self._st.disconnect_from()

    def _on_baud_changed(self, text: str) -> None:
        try:
            int(text)
        except ValueError:
            return
        self._st._baud_combo.setCurrentText(text)

    def _on_auto_connect_toggled(self, checked: bool) -> None:
        self._cfg.auto_connect = checked
        pool.save()

    def _on_reconnect_toggled(self, checked: bool) -> None:
        self._st._reconnect_enabled = checked
        self._cfg.auto_reconnect = checked
        pool.save()

    def _on_connection_changed(self) -> None:
        connected = self._st.serial.is_connected()
        if connected:
            port = self._st.serial.connected_port or ""
            self._status_lbl.setText(f"Connected  —  {port}")
            self._status_lbl.setStyleSheet(_CONNECTED_STYLE)
        else:
            self._status_lbl.setText("Disconnected")
            self._status_lbl.setStyleSheet(_DISCONNECTED_STYLE)
        self._connect_btn.setEnabled(not connected)
        self._disconnect_btn.setEnabled(connected)
        self._port_combo.setEnabled(not connected)
        self._baud_combo.setEnabled(not connected)
        self._bytesize_combo.setEnabled(not connected)
        self._parity_combo.setEnabled(not connected)
        self._stopbits_combo.setEnabled(not connected)
        self._flow_combo.setEnabled(not connected)
        # Mirror reconnect state (might have changed from terminal widget).
        self._reconnect_cb.blockSignals(True)
        self._reconnect_cb.setChecked(self._st._reconnect_enabled)
        self._reconnect_cb.blockSignals(False)

    def reload_from_config(self) -> None:
        """Sync all serial params from the pool after a profile switch."""
        self._refresh_ports()
        self._baud_combo.setCurrentText(self._st._baud_combo.currentText())
        if self._cfg.bytesize:
            self._bytesize_combo.setCurrentText(self._cfg.bytesize)
        if self._cfg.parity:
            self._parity_combo.setCurrentText(self._cfg.parity)
        if self._cfg.stopbits:
            self._stopbits_combo.setCurrentText(self._cfg.stopbits)
        if self._cfg.flow_control:
            self._flow_combo.setCurrentText(self._cfg.flow_control)
        reconnect = self._cfg.auto_reconnect or False
        self._st._reconnect_enabled = reconnect
        self._reconnect_cb.blockSignals(True)
        self._reconnect_cb.setChecked(reconnect)
        self._reconnect_cb.blockSignals(False)
        self._auto_connect_cb.blockSignals(True)
        self._auto_connect_cb.setChecked(self._cfg.auto_connect or False)
        self._auto_connect_cb.blockSignals(False)

    def _save_config(self) -> None:
        try:
            self._cfg.baudrate = int(self._baud_combo.currentText())
        except ValueError:
            pass
        self._cfg.bytesize = self._bytesize_combo.currentText()
        self._cfg.parity = self._parity_combo.currentText()
        self._cfg.stopbits = self._stopbits_combo.currentText()
        self._cfg.flow_control = self._flow_combo.currentText()
        self._cfg.auto_reconnect = self._reconnect_cb.isChecked()
        pool.save()

    def closeEvent(self, event) -> None:
        self._save_config()
        self._port_poll.stop()
        super().closeEvent(event)
