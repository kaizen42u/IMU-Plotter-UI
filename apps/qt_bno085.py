"""BNO085 sensor control pane — init/deinit, get, offset, tare."""

import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config_store import pool
from qt_gpio_combobox import QtGPIOCombobox
from qt_spinbox import HSpinBox

EVENT_ROTATION = "0x10"
EVENT_ACCEL    = "0x11"

# `bno085 get` inline response, e.g.:
#   BNO085 [ 28993 ms] | Yaw: 46.03° Pitch: -1.34° Roll: -1.06° |
#   X Accel: 0.01 m/s² Y Accel: 0.01 m/s² Z Accel: -0.01 m/s²
_RE_GET = re.compile(
    r"Yaw:\s*(-?[\d.]+).*?Pitch:\s*(-?[\d.]+).*?Roll:\s*(-?[\d.]+)"
    r".*?X\s*Accel:\s*(-?[\d.]+).*?Y\s*Accel:\s*(-?[\d.]+).*?Z\s*Accel:\s*(-?[\d.]+)",
    re.IGNORECASE,
)

_VAL_W = 75  # fixed width for value labels


def _val_label() -> QLabel:
    lbl = QLabel("—")
    lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    lbl.setFixedWidth(_VAL_W)
    lbl.setStyleSheet("font-weight: bold; font-size: 12px;")
    return lbl


class BNO085Window(QWidget):
    """BNO085 sensor control — init/deinit, get, offset, tare."""

    def __init__(self, serial_terminal, parser=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("BNO085")
        self.setWindowFlag(Qt.WindowType.Window)
        self._st          = serial_terminal
        self._parser      = parser
        self._cfg         = pool.section("bno085", defaults={"tx_gpio": "GPIO5", "rx_gpio": "GPIO4"})
        self._initialized   = False
        self._offset_btns:  list[QPushButton] = []
        self._tare_btns:    list[QPushButton] = []
        self._timer         = QTimer(self)
        self._timer.timeout.connect(self._do_get)

        self._build_ui()

        serial_terminal.register_event_callback(EVENT_ROTATION, self._on_rotation_event)
        serial_terminal.register_event_callback(EVENT_ACCEL,    self._on_accel_event)
        serial_terminal.register_connection_state_callback(self._on_connection_changed)
        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ── Top bar ───────────────────────────────────────────────────
        bar = QHBoxLayout()

        bar.addWidget(QLabel("TX:"))
        self._tx_combo = QtGPIOCombobox()
        self._tx_combo.set_gpio(self._cfg.tx_gpio)
        self._tx_combo.setFixedWidth(100)
        bar.addWidget(self._tx_combo)

        bar.addWidget(QLabel("RX:"))
        self._rx_combo = QtGPIOCombobox()
        self._rx_combo.set_gpio(self._cfg.rx_gpio)
        self._rx_combo.setFixedWidth(100)
        bar.addWidget(self._rx_combo)

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

        get_row = QHBoxLayout()
        self._get_btn = QPushButton("Get")
        self._get_btn.clicked.connect(self._do_get)
        get_row.addWidget(self._get_btn)
        self._auto_cb = QCheckBox("Auto")
        self._auto_cb.toggled.connect(self._on_auto_toggled)
        get_row.addWidget(self._auto_cb)
        self._interval_spin = HSpinBox()
        self._interval_spin.setRange(100, 10_000)
        self._interval_spin.setValue(500)
        self._interval_spin.setSingleStep(100)
        self._interval_spin.setSuffix(" ms")
        self._interval_spin.valueChanged.connect(
            lambda ms: self._timer.setInterval(ms) if self._timer.isActive() else None
        )
        get_row.addWidget(self._interval_spin)
        get_row.addStretch()
        data_lay.addLayout(get_row)

        # Rotation row
        rot_row = QHBoxLayout()
        rot_row.addWidget(QLabel("Yaw"))
        self._yaw_lbl   = _val_label()
        rot_row.addWidget(self._yaw_lbl)
        rot_row.addWidget(QLabel("°"))
        rot_row.addSpacing(12)
        rot_row.addWidget(QLabel("Pitch"))
        self._pitch_lbl = _val_label()
        rot_row.addWidget(self._pitch_lbl)
        rot_row.addWidget(QLabel("°"))
        rot_row.addSpacing(12)
        rot_row.addWidget(QLabel("Roll"))
        self._roll_lbl  = _val_label()
        rot_row.addWidget(self._roll_lbl)
        rot_row.addWidget(QLabel("°"))
        rot_row.addStretch()
        data_lay.addLayout(rot_row)

        # Accel row
        acc_row = QHBoxLayout()
        acc_row.addWidget(QLabel("Accel X"))
        self._ax_lbl = _val_label()
        acc_row.addWidget(self._ax_lbl)
        acc_row.addWidget(QLabel("m/s²"))
        acc_row.addSpacing(12)
        acc_row.addWidget(QLabel("Y"))
        self._ay_lbl = _val_label()
        acc_row.addWidget(self._ay_lbl)
        acc_row.addWidget(QLabel("m/s²"))
        acc_row.addSpacing(12)
        acc_row.addWidget(QLabel("Z"))
        self._az_lbl = _val_label()
        acc_row.addWidget(self._az_lbl)
        acc_row.addWidget(QLabel("m/s²"))
        acc_row.addStretch()
        data_lay.addLayout(acc_row)

        root.addWidget(data_box)

        # ── Offset ────────────────────────────────────────────────────
        offset_box = QGroupBox("Mounting Offset")
        offset_row = QHBoxLayout(offset_box)
        for label, mode in [("Set All (3D)", "all"), ("Set Yaw Only", "yaw"), ("Clear", "clear")]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _, m=mode: self._do_offset(m))
            offset_row.addWidget(btn)
            self._offset_btns.append(btn)
        offset_row.addStretch()
        root.addWidget(offset_box)

        # ── Tare ──────────────────────────────────────────────────────
        tare_box = QGroupBox("Tare")
        tare_row = QHBoxLayout(tare_box)
        for label, mode in [("Tare XYZ", "xyz"), ("Tare Z", "z"), ("Clear Tare", "clear")]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _, m=mode: self._do_tare(m))
            tare_row.addWidget(btn)
            self._tare_btns.append(btn)
        tare_row.addStretch()
        root.addWidget(tare_box)

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
        tx = self._gpio_str(self._tx_combo)
        rx = self._gpio_str(self._rx_combo)
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(msg)
            if status == "OK":
                self._initialized = True
                self._save_config()
                self._update_state()
                # The sensor resets during init, so (re-)enable the rotation and
                # linear-accel events now that it's up and streaming.
                self._send(f"event enable {EVENT_ROTATION}")
                self._send(f"event enable {EVENT_ACCEL}")
        self._send(f"bno085 init {tx} {rx}", on_resp)

    def _do_deinit(self) -> None:
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(msg)
            self._initialized = False
            self._timer.stop()
            self._auto_cb.blockSignals(True)
            self._auto_cb.setChecked(False)
            self._auto_cb.blockSignals(False)
            self._update_state()
        self._send("bno085 deinit", on_resp)

    def _do_get(self) -> None:
        if not self._initialized:
            return
        def on_resp(lines, status):
            if status != "OK":
                self._status_lbl.setText(next((l.strip() for l in lines if l.strip()), "FAIL"))
                return
            # `get` now returns orientation + accel inline on one line.
            for line in lines:
                m = _RE_GET.search(line)
                if m:
                    y, p, r, ax, ay, az = (float(v) for v in m.groups())
                    self._set_orientation(y, p, r)
                    self._set_accel(ax, ay, az)
                    break
        self._send("bno085 get", on_resp)

    # ------------------------------------------------------------------
    def _set_orientation(self, yaw: float, pitch: float, roll: float) -> None:
        self._yaw_lbl.setText(f"{yaw:.1f}")
        self._pitch_lbl.setText(f"{pitch:.1f}")
        self._roll_lbl.setText(f"{roll:.1f}")

    def _set_accel(self, x: float, y: float, z: float) -> None:
        self._ax_lbl.setText(f"{x:.3f}")
        self._ay_lbl.setText(f"{y:.3f}")
        self._az_lbl.setText(f"{z:.3f}")

    def _do_offset(self, mode: str) -> None:
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(f"Offset {mode}: {msg}")
        self._send(f"bno085 offset {mode}", on_resp)

    def _do_tare(self, mode: str) -> None:
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(f"Tare {mode}: {msg}")
        self._send(f"bno085 tare {mode}", on_resp)

    # ------------------------------------------------------------------
    def _on_rotation_event(self, timestamp: str, data: str) -> None:
        try:
            parts = data.split()
            if len(parts) >= 3:
                self._set_orientation(float(parts[0]), float(parts[1]), float(parts[2]))
        except Exception:
            pass

    def _on_accel_event(self, timestamp: str, data: str) -> None:
        try:
            parts = data.split()
            if len(parts) >= 3:
                self._set_accel(float(parts[0]), float(parts[1]), float(parts[2]))
        except Exception:
            pass

    # ------------------------------------------------------------------
    def _on_auto_toggled(self, on: bool) -> None:
        if on and self._initialized:
            self._timer.start(self._interval_spin.value())
            self._do_get()
        else:
            self._timer.stop()

    def _on_connection_changed(self) -> None:
        connected = self._st.serial.is_connected()
        self._init_btn.setEnabled(connected)
        self._deinit_btn.setEnabled(connected and self._initialized)
        if not connected:
            self._initialized = False
            self._timer.stop()
        self._update_state()

    def _update_state(self) -> None:
        active = self._initialized
        self._get_btn.setEnabled(active)
        self._auto_cb.setEnabled(active)
        self._interval_spin.setEnabled(active)
        for btn in self._offset_btns + self._tare_btns:
            btn.setEnabled(active)
        if not active:
            self._timer.stop()
            self._auto_cb.blockSignals(True)
            self._auto_cb.setChecked(False)
            self._auto_cb.blockSignals(False)

    # ------------------------------------------------------------------
    def _save_config(self) -> None:
        self._cfg.tx_gpio = self._tx_combo.currentText()
        self._cfg.rx_gpio = self._rx_combo.currentText()
        pool.save()

    def closeEvent(self, event) -> None:
        self._timer.stop()
        super().closeEvent(event)
