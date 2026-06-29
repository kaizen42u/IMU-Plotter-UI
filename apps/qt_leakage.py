"""Water leakage sensor window (Qt port of apps/leakageApp.py)."""

from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config_store import pool
EVENT_LEAKAGE_STATUS = "0x30"

_STATE_MAP = {0: ("Dry", "green"), 1: ("Moist", "orange"), 2: ("Wet", "darkorange"), 3: ("Critical", "red")}
_HEALTH_MAP = {0: ("OK", "green"), 1: ("Stuck", "orange"), 2: ("Fault", "red")}


class LeakageWindow(QWidget):
    GPIO_OPTIONS = [f"GPIO{i}" for i in range(22)] + [f"GPIO{i}" for i in range(26, 49)]

    def __init__(self, serial_terminal, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Leakage Sensor")
        self.serial_terminal = serial_terminal

        self._cfg = pool.section("leakage", defaults={"gpio": "GPIO2", "calibration_scans": 3})
        self._gpio = self._cfg.gpio
        self._calib_scans = self._cfg.calibration_scans
        self._initialized = False
        self._monitoring = False

        serial_terminal.register_event_callback(EVENT_LEAKAGE_STATUS, self._on_leakage_status)
        serial_terminal.register_connection_state_callback(self._on_connection_changed)

        self._build_ui()
        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Config
        cfg_box = QGroupBox("Configuration")
        cfg_layout = QHBoxLayout(cfg_box)
        cfg_layout.addWidget(QLabel("GPIO:"))
        self._gpio_combo = QComboBox()
        self._gpio_combo.addItems(self.GPIO_OPTIONS)
        self._gpio_combo.setCurrentText(self._gpio)
        cfg_layout.addWidget(self._gpio_combo)
        cfg_layout.addWidget(QLabel("Calib. Scans:"))
        self._scans_entry = QLineEdit(str(self._calib_scans))
        self._scans_entry.setFixedWidth(50)
        cfg_layout.addWidget(self._scans_entry)
        cfg_layout.addStretch()
        root.addWidget(cfg_box)

        # Status
        status_box = QGroupBox("Sensor Status")
        status_layout = QVBoxLayout(status_box)

        def _row(label: str, attr: str, color: str) -> QLabel:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            lbl = QLabel("—")
            lbl.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {color};")
            setattr(self, attr, lbl)
            row.addWidget(lbl)
            row.addStretch()
            status_layout.addLayout(row)
            return lbl

        _row("Raw Value:", "_raw_lbl", "blue")
        _row("Change %:", "_change_lbl", "teal")
        _row("State:", "_state_lbl", "green")
        _row("Health:", "_health_lbl", "orange")
        root.addWidget(status_box)

        # Control
        ctrl_box = QGroupBox("Control")
        ctrl_layout = QHBoxLayout(ctrl_box)
        self._init_btn = QPushButton("Init")
        self._init_btn.clicked.connect(self._leakage_init)
        self._deinit_btn = QPushButton("Deinit")
        self._deinit_btn.clicked.connect(self._leakage_deinit)
        ctrl_layout.addWidget(self._init_btn)
        ctrl_layout.addWidget(self._deinit_btn)
        ctrl_layout.addStretch()
        root.addWidget(ctrl_box)

        self.setMinimumWidth(400)

    # ------------------------------------------------------------------
    def _on_leakage_status(self, timestamp: str, data: str) -> None:
        try:
            parts = data.split()
            if len(parts) >= 4:
                raw = int(float(parts[0]))
                change = float(parts[1])
                state = int(parts[2])
                health = int(parts[3])

                self._raw_lbl.setText(str(raw))
                self._change_lbl.setText(f"{change:.2f}%")

                s_text, s_color = _STATE_MAP.get(state, (f"Unknown({state})", "gray"))
                self._state_lbl.setText(s_text)
                self._state_lbl.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {s_color};")

                h_text, h_color = _HEALTH_MAP.get(health, (f"Unknown({health})", "gray"))
                self._health_lbl.setText(h_text)
                self._health_lbl.setStyleSheet(f"font-weight: bold; font-size: 13px; color: {h_color};")
        except Exception as e:
            print(f"[Leakage] event error: {e}")

    def _leakage_init(self) -> None:
        if not self.serial_terminal.serial.is_connected():
            return
        self._gpio = self._gpio_combo.currentText()
        self._save_config()
        self.serial_terminal.send_command(f"leakage init {self._gpio}\n")
        self._initialized = True
        try:
            scans = int(self._scans_entry.text())
        except ValueError:
            scans = 3
        self.serial_terminal.send_command(f"leakage calibrate {scans}\n")
        self.serial_terminal.send_command("leakage enable\n")
        self._monitoring = True

    def _leakage_deinit(self) -> None:
        if not self.serial_terminal.serial.is_connected():
            return
        self.serial_terminal.send_command("leakage disable\n")
        self.serial_terminal.send_command("leakage deinit\n")
        self._monitoring = False
        self._initialized = False

    def _on_connection_changed(self) -> None:
        connected = self.serial_terminal.serial.is_connected()
        self._init_btn.setEnabled(connected)
        self._deinit_btn.setEnabled(connected)

    def _save_config(self) -> None:
        self._cfg.gpio = self._gpio
        try:
            self._cfg.calibration_scans = int(self._scans_entry.text())
        except ValueError:
            pass
        pool.save()

    def closeEvent(self, event) -> None:
        self._save_config()
        super().closeEvent(event)
