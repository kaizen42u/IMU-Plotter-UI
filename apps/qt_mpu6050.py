"""MPU6050 sensor control pane — init/deinit, live values, calibration."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config_store import pool
from qt_gpio_combobox import QtGPIOCombobox

EVENT_GYRO   = "0x14"
EVENT_ACCEL  = "0x15"
EVENT_SIMPLE = "0x18"

_VAL_W = 75  # fixed width for value labels


def _val_label() -> QLabel:
    lbl = QLabel("—")
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    lbl.setFixedWidth(_VAL_W)
    lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
    return lbl


class MPU6050Window(QWidget):
    """MPU6050 sensor control — init/deinit, live values, calibration."""

    def __init__(self, serial_terminal, parser=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MPU6050")
        self.setWindowFlag(Qt.WindowType.Window)
        self._st     = serial_terminal
        self._parser = parser
        self._cfg    = pool.section("mpu6050", defaults={"sda_gpio": "GPIO37", "scl_gpio": "GPIO36"})
        self._initialized = False
        self._cali_btns: list[QPushButton] = []

        self._build_ui()

        serial_terminal.register_event_callback(EVENT_GYRO,   self._on_gyro_event)
        serial_terminal.register_event_callback(EVENT_ACCEL,  self._on_accel_event)
        serial_terminal.register_event_callback(EVENT_SIMPLE, self._on_simple_event)
        serial_terminal.register_connection_state_callback(self._on_connection_changed)
        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ── Top bar ───────────────────────────────────────────────────
        bar = QHBoxLayout()

        bar.addWidget(QLabel("SDA:"))
        self._sda_combo = QtGPIOCombobox()
        self._sda_combo.set_gpio(self._cfg.sda_gpio)
        self._sda_combo.setFixedWidth(100)
        bar.addWidget(self._sda_combo)

        bar.addWidget(QLabel("SCL:"))
        self._scl_combo = QtGPIOCombobox()
        self._scl_combo.set_gpio(self._cfg.scl_gpio)
        self._scl_combo.setFixedWidth(100)
        bar.addWidget(self._scl_combo)

        bar.addSpacing(8)

        self._init_btn = QPushButton("Init")
        self._init_btn.clicked.connect(self._do_init)
        self._deinit_btn = QPushButton("Deinit")
        self._deinit_btn.clicked.connect(self._do_deinit)
        bar.addWidget(self._init_btn)
        bar.addWidget(self._deinit_btn)

        bar.addStretch()
        root.addLayout(bar)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self._status_lbl)

        # ── Sensor data ───────────────────────────────────────────────
        data_box = QGroupBox("Sensor Data")
        data_lay = QVBoxLayout(data_box)

        # Orientation row (event 0x18)
        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel("Yaw"))
        self._yaw_lbl = _val_label()
        rot_row.addWidget(self._yaw_lbl)
        rot_row.addWidget(QLabel("°"))
        rot_row.addSpacing(12)
        rot_row.addWidget(QLabel("Pitch"))
        self._pitch_lbl = _val_label()
        rot_row.addWidget(self._pitch_lbl)
        rot_row.addWidget(QLabel("°"))
        rot_row.addSpacing(12)
        rot_row.addWidget(QLabel("Roll"))
        self._roll_lbl = _val_label()
        rot_row.addWidget(self._roll_lbl)
        rot_row.addWidget(QLabel("°"))
        rot_row.addStretch()
        data_lay.addLayout(rot_row)

        # Gyro row (event 0x14)
        gyro_row = QHBoxLayout()
        gyro_row.addWidget(QLabel("Gyro X"))
        self._gx_lbl = _val_label()
        gyro_row.addWidget(self._gx_lbl)
        gyro_row.addWidget(QLabel("°/s"))
        gyro_row.addSpacing(12)
        gyro_row.addWidget(QLabel("Y"))
        self._gy_lbl = _val_label()
        gyro_row.addWidget(self._gy_lbl)
        gyro_row.addWidget(QLabel("°/s"))
        gyro_row.addSpacing(12)
        gyro_row.addWidget(QLabel("Z"))
        self._gz_lbl = _val_label()
        gyro_row.addWidget(self._gz_lbl)
        gyro_row.addWidget(QLabel("°/s"))
        gyro_row.addStretch()
        data_lay.addLayout(gyro_row)

        # Accel row (event 0x15)
        acc_row = QHBoxLayout()
        acc_row.addWidget(QLabel("Accel X"))
        self._ax_lbl = _val_label()
        acc_row.addWidget(self._ax_lbl)
        acc_row.addWidget(QLabel("G"))
        acc_row.addSpacing(12)
        acc_row.addWidget(QLabel("Y"))
        self._ay_lbl = _val_label()
        acc_row.addWidget(self._ay_lbl)
        acc_row.addWidget(QLabel("G"))
        acc_row.addSpacing(12)
        acc_row.addWidget(QLabel("Z"))
        self._az_lbl = _val_label()
        acc_row.addWidget(self._az_lbl)
        acc_row.addWidget(QLabel("G"))
        acc_row.addStretch()
        data_lay.addLayout(acc_row)

        root.addWidget(data_box)

        # ── Calibration ───────────────────────────────────────────────
        cali_box = QGroupBox("Calibration")
        cali_row = QHBoxLayout(cali_box)
        for label, sensor in [("Calibrate Accel", "acc"), ("Calibrate Gyro", "gyro")]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _, s=sensor: self._do_cali(s))
            cali_row.addWidget(btn)
            self._cali_btns.append(btn)
        cali_row.addStretch()
        root.addWidget(cali_box)

        self.adjustSize()

    # ------------------------------------------------------------------
    def _send(self, cmd: str, callback=None) -> None:
        if self._parser is not None:
            self._parser.send(cmd, callback)
        elif self._st.serial.is_connected():
            self._st.send_command(cmd + "\n")

    def _gpio_str(self, combo: QtGPIOCombobox) -> str:
        gpio = combo.get_gpio()
        return str(int(gpio)) if gpio is not None else ""

    # ------------------------------------------------------------------
    def _do_init(self) -> None:
        sda = self._gpio_str(self._sda_combo)
        scl = self._gpio_str(self._scl_combo)
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(msg)
            if status == "OK":
                self._initialized = True
                self._save_config()
                self._update_state()
        self._send(f"mpu6050 init {sda} {scl}", on_resp)

    def _do_deinit(self) -> None:
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(msg)
            self._initialized = False
            self._update_state()
        self._send("mpu6050 deinit", on_resp)

    def _do_cali(self, sensor: str) -> None:
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(f"Cali {sensor}: {msg}")
        self._send(f"mpu6050 cali {sensor}", on_resp)

    # ------------------------------------------------------------------
    def _on_simple_event(self, timestamp: str, data: str) -> None:
        try:
            parts = data.split()
            if len(parts) >= 3:
                self._yaw_lbl.setText(f"{float(parts[0]):.1f}")
                self._pitch_lbl.setText(f"{float(parts[1]):.1f}")
                self._roll_lbl.setText(f"{float(parts[2]):.1f}")
        except Exception:
            pass

    def _on_gyro_event(self, timestamp: str, data: str) -> None:
        try:
            parts = data.split()
            if len(parts) >= 3:
                self._gx_lbl.setText(f"{float(parts[0]):.1f}")
                self._gy_lbl.setText(f"{float(parts[1]):.1f}")
                self._gz_lbl.setText(f"{float(parts[2]):.1f}")
        except Exception:
            pass

    def _on_accel_event(self, timestamp: str, data: str) -> None:
        try:
            parts = data.split()
            if len(parts) >= 3:
                self._ax_lbl.setText(f"{float(parts[0]):.3f}")
                self._ay_lbl.setText(f"{float(parts[1]):.3f}")
                self._az_lbl.setText(f"{float(parts[2]):.3f}")
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_connection_changed(self) -> None:
        connected = self._st.serial.is_connected()
        self._init_btn.setEnabled(connected)
        self._deinit_btn.setEnabled(connected and self._initialized)
        if not connected:
            self._initialized = False
        self._update_state()

    def _update_state(self) -> None:
        active = self._initialized
        self._deinit_btn.setEnabled(self._st.serial.is_connected() and active)
        self._sda_combo.setEnabled(not active)
        self._scl_combo.setEnabled(not active)
        for btn in self._cali_btns:
            btn.setEnabled(active)

    # ------------------------------------------------------------------
    def _save_config(self) -> None:
        self._cfg.sda_gpio = self._sda_combo.currentText()
        self._cfg.scl_gpio = self._scl_combo.currentText()
        pool.save()
