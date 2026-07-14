"""AM32 ESC direct UART configuration pane."""

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config_store import pool
from qt_gpio_combobox import QtGPIOCombobox
from qt_spinbox import HSpinBox

_BAUD_OPTIONS = ["19200", "38400", "57600", "115200"]

_BOOL_FIELDS = [
    ("reverse",                "Reverse Rotation"),
    ("complementary_pwm",      "Complementary PWM"),
    ("bidirectional",          "Bidirectional"),
    ("brake_on_stop",          "Brake on Stop"),
    ("stall_protection",       "Stall Protection"),
    ("sinusoidal_startup",     "Sinusoidal Startup"),
    ("telemetry_30ms",         "Telemetry 30ms"),
    ("hall_sensors",           "Hall Sensors"),
    ("stuck_rotor_protection", "Stuck Rotor Prot."),
]

# (key, label, min, max, step, suffix)
_NUM_FIELDS = [
    ("variable_pwm",        "Variable PWM Mode",    0,    2,  1,  ""),
    ("timing_advance",      "Timing Advance",        0,   42,  1,  ""),
    ("kv",                  "Motor KV",             40, 4000, 40,  " KV"),
    ("motor_poles",         "Motor Poles",           2,   64,  2,  ""),
    ("startup_power",       "Startup Power",        50,  150,  1,  ""),
    ("pwm_frequency",       "PWM Frequency",         8,  144,  1,  " kHz"),
    ("beep",                "Beep Volume",           0,   11,  1,  ""),
    ("stopped_brake_level", "Stopped Brake Level",   1,   10,  1,  ""),
    ("running_brake_level", "Running Brake Level",   1,   10,  1,  ""),
    ("sine_startup_range",  "Sine Startup Range",    5,   25,  1,  "%"),
    ("sine_mode_power",     "Sine Mode Power",       1,   10,  1,  ""),
]

_BOOL_COLS = 3

# The firmware's "AM32 decoded settings" block names fields differently from the
# `set` command keys used by this pane. Map read-output names → pane field keys.
_READ_BOOL_MAP = {
    "direction_reversed":     "reverse",
    "bidirectional_mode":     "bidirectional",
    "sinusoidal_startup":     "sinusoidal_startup",
    "complementary_pwm":      "complementary_pwm",
    "stuck_rotor_protection": "stuck_rotor_protection",
    "brake_on_stop":          "brake_on_stop",
    "stall_protection":       "stall_protection",
    "telemetry_30ms":         "telemetry_30ms",
    "hall_sensor_enable":     "hall_sensors",
}
_READ_NUM_MAP = {
    "timing_advance":        "timing_advance",
    "pwm_frequency":         "pwm_frequency",
    "startup_power":         "startup_power",
    "motor_poles":           "motor_poles",
    "beep_volume":           "beep",
    "sine_startup_range":    "sine_startup_range",
    "stopped_brake_level":   "stopped_brake_level",
    "running_brake_level":   "running_brake_level",
    "sine_mode_power":       "sine_mode_power",
    "variable_pwm_frequency": "variable_pwm",   # dev reports 0/1; pane spin is 0-2
    # "motor_kv_step" handled specially: value is "12 (approx 480 KV)"
}

# A decoded-settings line: "  [17] direction_reversed: off (0)"
_RE_DECODED = re.compile(r"^\s*\[\d+(?:-\d+)?\]\s*(\w+):\s*(.+?)\s*$")


class AM32Window(QWidget):
    """AM32 ESC direct UART config — probe, read, set named fields, dump/write."""

    def __init__(self, serial_terminal, parser=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("AM32 ESC Config")
        self.setWindowFlag(Qt.WindowType.Window)
        self._st     = serial_terminal
        self._parser = parser
        self._cfg    = pool.section("am32")
        self._read_done = False

        self._bool_cbs:  dict[str, QCheckBox] = {}
        self._num_spins: dict[str, HSpinBox]  = {}
        self._set_btns:  list[QPushButton]    = []

        self._build_ui()
        self._load_saved()
        serial_terminal.register_connection_state_callback(self._on_connection_changed)
        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ── Top bar ───────────────────────────────────────────────────
        bar = QHBoxLayout()

        bar.addWidget(QLabel("GPIO:"))
        self._gpio_combo = QtGPIOCombobox()
        self._gpio_combo.setFixedWidth(100)
        bar.addWidget(self._gpio_combo)

        bar.addWidget(QLabel("Baud:"))
        self._baud_combo = QComboBox()
        self._baud_combo.addItems(_BAUD_OPTIONS)
        self._baud_combo.setCurrentText("19200")
        self._baud_combo.setFixedWidth(90)
        bar.addWidget(self._baud_combo)

        self._baud_btn = QPushButton("Set Baud")
        self._baud_btn.clicked.connect(self._do_set_baud)
        bar.addWidget(self._baud_btn)

        bar.addSpacing(12)

        self._probe_btn = QPushButton("Probe")
        self._probe_btn.clicked.connect(self._do_probe)
        bar.addWidget(self._probe_btn)

        self._read_btn = QPushButton("Read Config")
        self._read_btn.clicked.connect(self._do_read)
        bar.addWidget(self._read_btn)

        bar.addStretch()
        root.addLayout(bar)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self._status_lbl)

        # ── Scrollable body ───────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)

        body = QWidget()
        body_lay = QVBoxLayout(body)
        body_lay.setSpacing(8)

        body_lay.addWidget(self._build_info_box())
        body_lay.addWidget(self._build_bool_box())
        body_lay.addWidget(self._build_num_box())
        body_lay.addWidget(self._build_advanced_box())
        body_lay.addStretch()

        scroll.setWidget(body)
        root.addWidget(scroll)

        self.setMinimumWidth(560)
        self.adjustSize()

    # ------------------------------------------------------------------
    def _build_info_box(self) -> QGroupBox:
        box = QGroupBox("ESC Info")
        lay = QVBoxLayout(box)
        self._info_text = QTextEdit()
        self._info_text.setReadOnly(True)
        self._info_text.setFixedHeight(80)
        self._info_text.setPlaceholderText("Press Probe or Read Config to populate…")
        lay.addWidget(self._info_text)
        return box

    def _build_bool_box(self) -> QGroupBox:
        box = QGroupBox("Boolean Settings")
        grid = QGridLayout(box)
        grid.setSpacing(6)
        for i, (key, label) in enumerate(_BOOL_FIELDS):
            cb = QCheckBox(label)
            cb.setEnabled(False)
            cb.toggled.connect(lambda state, k=key: self._do_set_bool(k, state))
            self._bool_cbs[key] = cb
            grid.addWidget(cb, i // _BOOL_COLS, i % _BOOL_COLS)
        return box

    def _build_num_box(self) -> QGroupBox:
        box = QGroupBox("Numeric Settings")
        form = QFormLayout(box)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        for key, label, lo, hi, step, suffix in _NUM_FIELDS:
            row = QHBoxLayout()
            spin = HSpinBox()
            spin.setRange(lo, hi)
            spin.setSingleStep(step)
            if suffix:
                spin.setSuffix(suffix)
            spin.setEnabled(False)
            self._num_spins[key] = spin
            row.addWidget(spin)
            btn = QPushButton("Set")
            btn.setFixedWidth(48)
            btn.setEnabled(False)
            btn.clicked.connect(lambda _, k=key: self._do_set_num(k))
            self._set_btns.append(btn)
            row.addWidget(btn)
            form.addRow(f"{label}:", row)
        return box

    def _build_advanced_box(self) -> QGroupBox:
        box = QGroupBox("Advanced")
        lay = QVBoxLayout(box)
        lay.setSpacing(6)

        # Dump row
        dump_row = QHBoxLayout()
        dump_row.addWidget(QLabel("Dump addr:"))
        self._dump_addr = QLineEdit("0x7c00")
        self._dump_addr.setFixedWidth(80)
        dump_row.addWidget(self._dump_addr)
        dump_row.addWidget(QLabel("len:"))
        self._dump_len = HSpinBox()
        self._dump_len.setRange(1, 256)
        self._dump_len.setValue(48)
        dump_row.addWidget(self._dump_len)
        self._dump_btn = QPushButton("Dump")
        self._dump_btn.clicked.connect(self._do_dump)
        dump_row.addWidget(self._dump_btn)
        dump_row.addStretch()
        lay.addLayout(dump_row)

        self._dump_out = QTextEdit()
        self._dump_out.setReadOnly(True)
        self._dump_out.setFixedHeight(60)
        self._dump_out.setPlaceholderText("Hex output…")
        self._dump_out.setFontFamily("monospace")
        lay.addWidget(self._dump_out)

        # Write row
        write_row = QHBoxLayout()
        write_row.addWidget(QLabel("Write addr:"))
        self._write_addr = QLineEdit("0x7c1e")
        self._write_addr.setFixedWidth(80)
        write_row.addWidget(self._write_addr)
        write_row.addWidget(QLabel("value:"))
        self._write_val = QLineEdit("0x00")
        self._write_val.setFixedWidth(60)
        write_row.addWidget(self._write_val)
        self._write_btn = QPushButton("Write & Verify")
        self._write_btn.clicked.connect(self._do_write)
        write_row.addWidget(self._write_btn)
        write_row.addStretch()
        lay.addLayout(write_row)

        return box

    # ------------------------------------------------------------------
    def _send(self, cmd: str, callback=None) -> None:
        if self._parser is not None:
            self._parser.send(cmd, callback)
        elif self._st.serial.is_connected():
            self._st.send_command(cmd + "\n")

    def _gpio_arg(self) -> str:
        gpio = self._gpio_combo.get_gpio()
        return str(int(gpio)) if gpio is not None else "14"

    def _base(self) -> str:
        return f"am32 {self._gpio_arg()}"

    def _set_status(self, msg: str) -> None:
        self._status_lbl.setText(msg)

    # ------------------------------------------------------------------
    def _do_set_baud(self) -> None:
        baud = self._baud_combo.currentText()
        def on_resp(lines, status):
            self._set_status(f"Baud → {baud}" if status == "OK"
                             else f"Baud failed: {next((l.strip() for l in lines if l.strip()), status)}")
        self._send(f"am32 baud {baud}", on_resp)

    def _do_probe(self) -> None:
        def on_resp(lines, status):
            self._info_text.setPlainText("\n".join(l for l in lines if l.strip()) or "(no response)")
            self._set_status("Probe OK." if status == "OK" else f"Probe failed: {status}")
        self._send(f"{self._base()} probe", on_resp)

    def _do_read(self) -> None:
        def on_resp(lines, status):
            self._info_text.setPlainText("\n".join(l for l in lines if l.strip()) or "(no response)")
            if status == "OK":
                self._read_done = True
                self._set_config_enabled(True)
                n = self._populate_from_read(lines)
                self._set_status(f"Config read — {n} field(s) loaded, unlocked.")
            else:
                self._set_status(f"Read failed: {next((l.strip() for l in lines if l.strip()), status)}")
        self._send(f"{self._base()} read", on_resp)

    # ------------------------------------------------------------------
    def _populate_from_read(self, lines: list[str]) -> int:
        """Parse the 'AM32 decoded settings' block and fill the UI widgets.

        Signals are blocked so populating doesn't fire a `set` command back.
        Returns the number of fields applied.
        """
        applied = 0
        for line in lines:
            m = _RE_DECODED.match(line)
            if not m:
                continue
            name, val = m.group(1), m.group(2)
            if name in _READ_BOOL_MAP:
                key = _READ_BOOL_MAP[name]
                cb = self._bool_cbs.get(key)
                if cb is not None:
                    on = "(1)" in val or val.strip().lower().startswith("on")
                    cb.blockSignals(True)
                    cb.setChecked(on)
                    cb.blockSignals(False)
                    applied += 1
            elif name == "motor_kv_step":
                mk = re.search(r"approx\s+(\d+)", val)
                if mk and self._set_spin("kv", int(mk.group(1))):
                    applied += 1
            elif name in _READ_NUM_MAP:
                num = self._parse_int(val)
                if num is not None and self._set_spin(_READ_NUM_MAP[name], num):
                    applied += 1
        return applied

    def _set_spin(self, key: str, value: int) -> bool:
        spin = self._num_spins.get(key)
        if spin is None:
            return False
        spin.blockSignals(True)
        spin.setValue(value)   # HSpinBox.setValue clamps to its range
        spin.blockSignals(False)
        return True

    @staticmethod
    def _parse_int(val: str):
        m = re.match(r"\s*(-?\d+)", val)          # leading integer ("18 kHz", "120 %")
        if m:
            return int(m.group(1))
        m = re.search(r"\((\d+)\)", val)          # parenthetical ("on (1)")
        return int(m.group(1)) if m else None

    def _do_set_bool(self, field: str, state: bool) -> None:
        if not self._read_done:
            return
        val = 1 if state else 0
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._set_status(f"{field} → {val}: {msg}")
        self._send(f"{self._base()} set {field} {val}", on_resp)

    def _do_set_num(self, field: str) -> None:
        if not self._read_done:
            return
        val = self._num_spins[field].value()
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._set_status(f"{field} → {val}: {msg}")
        self._send(f"{self._base()} set {field} {val}", on_resp)

    def _do_dump(self) -> None:
        addr = self._dump_addr.text().strip() or "0x7c00"
        length = self._dump_len.value()
        def on_resp(lines, status):
            self._dump_out.setPlainText("\n".join(l for l in lines if l.strip()) or "(empty)")
            self._set_status("Dump OK." if status == "OK" else f"Dump failed: {status}")
        self._send(f"{self._base()} dump {addr} {length}", on_resp)

    def _do_write(self) -> None:
        addr = self._write_addr.text().strip() or "0x7c1e"
        val  = self._write_val.text().strip() or "0x00"
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._set_status(f"Write {addr}={val}: {msg}")
        self._send(f"{self._base()} write {addr} {val}", on_resp)

    # ------------------------------------------------------------------
    def _set_config_enabled(self, enabled: bool) -> None:
        for cb in self._bool_cbs.values():
            cb.setEnabled(enabled)
        for sp in self._num_spins.values():
            sp.setEnabled(enabled)
        for btn in self._set_btns:
            btn.setEnabled(enabled)

    def _on_connection_changed(self) -> None:
        connected = self._st.serial.is_connected()
        self._probe_btn.setEnabled(connected)
        self._read_btn.setEnabled(connected)
        self._baud_btn.setEnabled(connected)
        self._dump_btn.setEnabled(connected)
        self._write_btn.setEnabled(connected)
        if not connected:
            self._read_done = False
            self._set_config_enabled(False)

    # ------------------------------------------------------------------
    def _load_saved(self) -> None:
        gpio = getattr(self._cfg, "gpio", None)
        if gpio:
            self._gpio_combo.set_gpio(gpio)
        baud = getattr(self._cfg, "baud", None)
        if baud and baud in _BAUD_OPTIONS:
            self._baud_combo.setCurrentText(baud)

    def closeEvent(self, event) -> None:
        gpio = self._gpio_combo.get_gpio()
        self._cfg.gpio = str(int(gpio)) if gpio is not None else ""
        self._cfg.baud = self._baud_combo.currentText()
        pool.save()
        super().closeEvent(event)
