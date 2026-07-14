"""INA228 power monitor pane — multi-device init/config, live readings via events."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from config_store import pool
from qt_gpio_combobox import QtGPIOCombobox
from qt_spinbox import HSpinBox

EVENT_BUS_VOLTAGE = "0x70"
EVENT_CURRENT     = "0x71"
EVENT_POWER       = "0x72"
EVENT_TEMPERATURE = "0x73"

_DEVICE_IDS = ["1", "2", "3", "4"]
_CT_US      = ["50", "84", "150", "280", "540", "1052", "2074", "4120"]
_AVG        = ["1", "4", "16", "64", "128", "256", "512", "1024"]
_READ_SUBS  = ["all", "bus", "shunt", "current", "power", "temp", "energy", "charge"]


def _big_label(color: str) -> QLabel:
    lbl = QLabel("—")
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setMinimumWidth(130)
    lbl.setStyleSheet(
        f"font-size: 22px; font-weight: bold; color: {color};"
        "background: #f0f0f0; border: 2px inset gray; padding: 4px;"
    )
    return lbl


class INA228Window(QWidget):
    """INA228 power monitor — init/deinit, start/stop poll, live V/A/W/°C, full config."""

    def __init__(self, serial_terminal, parser=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("INA228")
        self.setWindowFlag(Qt.WindowType.Window)
        self._st     = serial_terminal
        self._parser = parser
        self._cfg    = pool.section("ina228", defaults={
            "device_id": "1",
            "sda_gpio": "GPIO4", "scl_gpio": "GPIO5",
            "shunt_mohm": "2.0", "i2c_addr": "64", "max_current_a": "10.0",
            "adc_range": "1",
        })
        self._initialized = False
        self._running     = False
        self._set_widgets: list = []

        self._build_ui()

        serial_terminal.register_event_callback(EVENT_BUS_VOLTAGE, self._on_bus)
        serial_terminal.register_event_callback(EVENT_CURRENT,     self._on_current)
        serial_terminal.register_event_callback(EVENT_POWER,       self._on_power)
        serial_terminal.register_event_callback(EVENT_TEMPERATURE, self._on_temp)
        serial_terminal.register_connection_state_callback(self._on_connection_changed)
        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ── Top bar ───────────────────────────────────────────────────
        bar = QHBoxLayout()

        bar.addWidget(QLabel("Device:"))
        self._dev_combo = QComboBox()
        self._dev_combo.addItems(_DEVICE_IDS)
        self._dev_combo.setCurrentText(str(getattr(self._cfg, "device_id", "1")))
        self._dev_combo.setFixedWidth(50)
        bar.addWidget(self._dev_combo)

        bar.addSpacing(8)

        self._init_btn = QPushButton("Init")
        self._init_btn.clicked.connect(self._do_init)
        bar.addWidget(self._init_btn)

        self._deinit_btn = QPushButton("Deinit")
        self._deinit_btn.clicked.connect(self._do_deinit)
        bar.addWidget(self._deinit_btn)

        bar.addSpacing(8)

        self._start_btn = QPushButton("Start")
        self._start_btn.clicked.connect(self._do_start)
        bar.addWidget(self._start_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.clicked.connect(self._do_stop)
        bar.addWidget(self._stop_btn)

        bar.addStretch()
        root.addLayout(bar)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self._status_lbl)

        # ── Init config ───────────────────────────────────────────────
        cfg_box = QGroupBox("Init Config")
        cfg_row = QHBoxLayout(cfg_box)

        cfg_row.addWidget(QLabel("SDA:"))
        self._sda_combo = QtGPIOCombobox()
        self._sda_combo.set_gpio(self._cfg.sda_gpio)
        self._sda_combo.setFixedWidth(100)
        cfg_row.addWidget(self._sda_combo)

        cfg_row.addWidget(QLabel("SCL:"))
        self._scl_combo = QtGPIOCombobox()
        self._scl_combo.set_gpio(self._cfg.scl_gpio)
        self._scl_combo.setFixedWidth(100)
        cfg_row.addWidget(self._scl_combo)

        cfg_row.addWidget(QLabel("Shunt:"))
        self._shunt_edit = QLineEdit(str(self._cfg.shunt_mohm))
        self._shunt_edit.setFixedWidth(60)
        cfg_row.addWidget(self._shunt_edit)
        cfg_row.addWidget(QLabel("mΩ"))

        cfg_row.addWidget(QLabel("Addr:"))
        self._addr_spin = HSpinBox()
        self._addr_spin.setRange(8, 119)
        self._addr_spin.setValue(int(float(self._cfg.i2c_addr)))
        self._addr_spin.setFixedWidth(70)
        cfg_row.addWidget(self._addr_spin)

        cfg_row.addWidget(QLabel("Max I:"))
        self._maxi_edit = QLineEdit(str(self._cfg.max_current_a))
        self._maxi_edit.setFixedWidth(60)
        cfg_row.addWidget(self._maxi_edit)
        cfg_row.addWidget(QLabel("A"))

        cfg_row.addWidget(QLabel("Range:"))
        self._range_combo = QComboBox()
        self._range_combo.addItem("±40.96 mV", "1")
        self._range_combo.addItem("±163.84 mV", "0")
        if str(self._cfg.adc_range) == "0":
            self._range_combo.setCurrentIndex(1)
        self._range_combo.setFixedWidth(110)
        cfg_row.addWidget(self._range_combo)

        cfg_row.addStretch()
        root.addWidget(cfg_box)

        # ── Live readings ─────────────────────────────────────────────
        read_box = QGroupBox("Readings")
        read_grid = QHBoxLayout(read_box)
        self._bus_lbl  = _big_label("#c0392b")
        self._cur_lbl  = _big_label("#16a085")
        self._pow_lbl  = _big_label("#8e44ad")
        self._temp_lbl = _big_label("#d35400")
        for caption, lbl in [
            ("Bus", self._bus_lbl), ("Current", self._cur_lbl),
            ("Power", self._pow_lbl), ("Temp", self._temp_lbl),
        ]:
            col = QVBoxLayout()
            cap = QLabel(caption)
            cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(cap)
            col.addWidget(lbl)
            read_grid.addLayout(col)
        root.addWidget(read_box)

        # ── Settings (ina228 set …) ───────────────────────────────────
        set_box = QGroupBox("Settings")
        set_form = QFormLayout(set_box)
        set_form.setHorizontalSpacing(12)
        set_form.setVerticalSpacing(4)

        def add_set_row(label: str, field: str, widget, value_getter) -> None:
            row = QHBoxLayout()
            row.addWidget(widget)
            btn = QPushButton("Set")
            btn.setFixedWidth(48)
            btn.clicked.connect(lambda _, f=field, g=value_getter: self._do_set(f, g()))
            row.addWidget(btn)
            row.addStretch()
            set_form.addRow(f"{label}:", row)
            self._set_widgets += [widget, btn]

        self._mode_spin = HSpinBox()
        self._mode_spin.setRange(0, 15)
        self._mode_spin.setValue(15)
        self._mode_spin.setFixedWidth(70)
        add_set_row("Mode", "mode", self._mode_spin, self._mode_spin.value)

        def ct_combo() -> QComboBox:
            c = QComboBox()
            c.addItems(_CT_US)
            c.setCurrentText("1052")
            c.setFixedWidth(80)
            return c

        self._vbusct_combo = ct_combo()
        add_set_row("VBUSCT (µs)", "vbusct", self._vbusct_combo, self._vbusct_combo.currentText)
        self._vshct_combo = ct_combo()
        add_set_row("VSHCT (µs)", "vshct", self._vshct_combo, self._vshct_combo.currentText)
        self._vtct_combo = ct_combo()
        add_set_row("VTCT (µs)", "vtct", self._vtct_combo, self._vtct_combo.currentText)

        self._avg_combo = QComboBox()
        self._avg_combo.addItems(_AVG)
        self._avg_combo.setFixedWidth(80)
        add_set_row("AVG (samples)", "avg", self._avg_combo, self._avg_combo.currentText)

        self._adcrange_combo = QComboBox()
        self._adcrange_combo.addItem("1 (±40.96 mV)", "1")
        self._adcrange_combo.addItem("0 (±163.84 mV)", "0")
        self._adcrange_combo.setFixedWidth(130)
        add_set_row("ADC Range", "adc_range", self._adcrange_combo, self._adcrange_combo.currentData)

        self._tempco_spin = HSpinBox()
        self._tempco_spin.setRange(0, 16383)
        self._tempco_spin.setFixedWidth(90)
        add_set_row("Tempco (ppm/°C)", "tempco", self._tempco_spin, self._tempco_spin.value)

        # calibration: derive Rshunt from a known target current
        cal_row = QHBoxLayout()
        self._cal_edit = QLineEdit("1.0")
        self._cal_edit.setFixedWidth(70)
        cal_row.addWidget(self._cal_edit)
        cal_row.addWidget(QLabel("A"))
        cal_btn = QPushButton("Calibrate")
        cal_btn.setFixedWidth(80)
        cal_btn.clicked.connect(
            lambda: self._do_set("calibration", self._cal_edit.text().strip() or "1.0"))
        cal_row.addWidget(cal_btn)
        cal_row.addStretch()
        set_form.addRow("Cal. current:", cal_row)
        self._set_widgets += [self._cal_edit, cal_btn]

        root.addWidget(set_box)

        # ── Manual read / dump ────────────────────────────────────────
        adv_box = QGroupBox("Manual")
        adv_lay = QVBoxLayout(adv_box)
        btn_row = QHBoxLayout()

        self._read_sub_combo = QComboBox()
        self._read_sub_combo.addItems(_READ_SUBS)
        self._read_sub_combo.setFixedWidth(90)
        btn_row.addWidget(self._read_sub_combo)

        self._read_btn = QPushButton("Read")
        self._read_btn.clicked.connect(self._do_read)
        btn_row.addWidget(self._read_btn)

        self._dump_btn = QPushButton("Dump Registers")
        self._dump_btn.clicked.connect(self._do_dump)
        btn_row.addWidget(self._dump_btn)
        btn_row.addStretch()
        adv_lay.addLayout(btn_row)

        self._out_text = QTextEdit()
        self._out_text.setReadOnly(True)
        self._out_text.setFixedHeight(90)
        self._out_text.setFontFamily("monospace")
        self._out_text.setPlaceholderText("Read / Dump output…")
        adv_lay.addWidget(self._out_text)
        root.addWidget(adv_box)

        self.adjustSize()

    # ------------------------------------------------------------------
    def _send(self, cmd: str, callback=None) -> None:
        if self._parser is not None:
            self._parser.send(cmd, callback)
        elif self._st.serial.is_connected():
            self._st.send_command(cmd + "\n")

    def _dev(self) -> str:
        return self._dev_combo.currentText()

    def _gpio_str(self, combo: QtGPIOCombobox) -> str:
        gpio = combo.get_gpio()
        return str(int(gpio)) if gpio is not None else ""

    # ------------------------------------------------------------------
    def _do_init(self) -> None:
        sda   = self._gpio_str(self._sda_combo)
        scl   = self._gpio_str(self._scl_combo)
        shunt = self._shunt_edit.text().strip() or "2.0"
        addr  = self._addr_spin.value()
        maxi  = self._maxi_edit.text().strip() or "10.0"
        rng   = self._range_combo.currentData()
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(msg)
            if status == "OK":
                self._initialized = True
                self._save_config()
                self._update_state()
        self._send(f"ina228 {self._dev()} init {sda} {scl} {shunt} {addr} {maxi} {rng}", on_resp)

    def _do_deinit(self) -> None:
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(msg)
            self._initialized = False
            self._running = False
            self._clear_readings()
            self._update_state()
        self._send(f"ina228 {self._dev()} deinit", on_resp)

    def _do_start(self) -> None:
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(msg)
            if status == "OK":
                self._running = True
                self._update_state()
        self._send(f"ina228 {self._dev()} start", on_resp)

    def _do_stop(self) -> None:
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(msg)
            self._running = False
            self._update_state()
        self._send(f"ina228 {self._dev()} stop", on_resp)

    def _do_set(self, field: str, value) -> None:
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(f"set {field} {value}: {msg}")
        self._send(f"ina228 {self._dev()} set {field} {value}", on_resp)

    def _do_read(self) -> None:
        sub = self._read_sub_combo.currentText()
        def on_resp(lines, status):
            self._out_text.setPlainText(
                "\n".join(l for l in lines if l.strip()) or "(no response)")
            self._status_lbl.setText(
                f"Read {sub} OK." if status == "OK" else f"Read {sub} failed: {status}")
        self._send(f"ina228 {self._dev()} read {sub}", on_resp)

    def _do_dump(self) -> None:
        def on_resp(lines, status):
            self._out_text.setPlainText(
                "\n".join(l for l in lines if l.strip()) or "(no response)")
            self._status_lbl.setText("Dump OK." if status == "OK" else f"Dump failed: {status}")
        self._send(f"ina228 {self._dev()} dump", on_resp)

    # ------------------------------------------------------------------
    def _event_value(self, data: str) -> float | None:
        """Events may carry '<value>' or '<device_id> <value>' — handle both."""
        parts = data.split()
        try:
            if len(parts) >= 2:
                if parts[0] == self._dev():
                    return float(parts[1])
                return None  # event belongs to another device
            if len(parts) == 1:
                return float(parts[0])
        except ValueError:
            pass
        return None

    def _on_bus(self, timestamp: str, data: str) -> None:
        v = self._event_value(data)
        if v is not None:
            self._bus_lbl.setText(f"{v:.3f} V")

    def _on_current(self, timestamp: str, data: str) -> None:
        # Firmware reports current in mA (e.g. "1 686.035 mA").
        v = self._event_value(data)
        if v is not None:
            self._cur_lbl.setText(f"{v:.1f} mA")

    def _on_power(self, timestamp: str, data: str) -> None:
        v = self._event_value(data)
        if v is not None:
            self._pow_lbl.setText(f"{v:.3f} W")

    def _on_temp(self, timestamp: str, data: str) -> None:
        v = self._event_value(data)
        if v is not None:
            self._temp_lbl.setText(f"{v:.1f} °C")

    def _clear_readings(self) -> None:
        for lbl in (self._bus_lbl, self._cur_lbl, self._pow_lbl, self._temp_lbl):
            lbl.setText("—")

    # ------------------------------------------------------------------
    def _on_connection_changed(self) -> None:
        if not self._st.serial.is_connected():
            self._initialized = False
            self._running = False
            self._clear_readings()
        self._update_state()

    def _update_state(self) -> None:
        connected = self._st.serial.is_connected()
        active    = self._initialized
        self._init_btn.setEnabled(connected)
        self._deinit_btn.setEnabled(connected and active)
        self._start_btn.setEnabled(connected and active and not self._running)
        self._stop_btn.setEnabled(connected and active and self._running)
        self._read_btn.setEnabled(connected and active)
        self._dump_btn.setEnabled(connected and active)
        for w in (self._sda_combo, self._scl_combo, self._shunt_edit,
                  self._addr_spin, self._maxi_edit, self._range_combo):
            w.setEnabled(not active)
        for w in self._set_widgets:
            w.setEnabled(connected and active)

    # ------------------------------------------------------------------
    def _save_config(self) -> None:
        self._cfg.device_id     = self._dev()
        self._cfg.sda_gpio      = self._sda_combo.currentText()
        self._cfg.scl_gpio      = self._scl_combo.currentText()
        self._cfg.shunt_mohm    = self._shunt_edit.text().strip()
        self._cfg.i2c_addr      = str(self._addr_spin.value())
        self._cfg.max_current_a = self._maxi_edit.text().strip()
        self._cfg.adc_range     = self._range_combo.currentData()
        pool.save()
