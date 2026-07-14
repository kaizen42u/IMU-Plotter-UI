"""VC288 voltage/current sensor window."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config_store import pool
from qt_gpio_combobox import QtGPIOCombobox


class _ConfigDialog(QDialog):
    """Calibration coefficients for voltage and current channels."""

    def __init__(self, cfg, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("VC288 Configure")
        self.setModal(True)
        self._cfg = cfg

        root = QVBoxLayout(self)
        root.setSpacing(10)

        # ── Voltage ───────────────────────────────────────────────────
        v_box = QGroupBox("Voltage Calibration")
        v_form = QFormLayout(v_box)
        self._v_slope  = self._field(cfg.voltage_slope)
        self._v_offset = self._field(cfg.voltage_offset)
        self._v_x2     = self._field(cfg.voltage_x2)
        v_form.addRow("Slope:",  self._v_slope)
        v_form.addRow("Offset:", self._v_offset)
        v_form.addRow("X²:",     self._v_x2)
        root.addWidget(v_box)

        # ── Current ───────────────────────────────────────────────────
        a_box = QGroupBox("Current Calibration")
        a_form = QFormLayout(a_box)
        self._a_slope  = self._field(cfg.current_slope)
        self._a_offset = self._field(cfg.current_offset)
        self._a_x2     = self._field(cfg.current_x2)
        a_form.addRow("Slope:",  self._a_slope)
        a_form.addRow("Offset:", self._a_offset)
        a_form.addRow("X²:",     self._a_x2)
        root.addWidget(a_box)

        # ── Buttons ───────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self.adjustSize()

    @staticmethod
    def _field(value: float) -> QLineEdit:
        w = QLineEdit(f"{value:.6g}")
        w.setFixedWidth(130)
        return w

    def _on_ok(self) -> None:
        try:
            self._cfg.voltage_slope  = float(self._v_slope.text())
            self._cfg.voltage_offset = float(self._v_offset.text())
            self._cfg.voltage_x2     = float(self._v_x2.text())
            self._cfg.current_slope  = float(self._a_slope.text())
            self._cfg.current_offset = float(self._a_offset.text())
            self._cfg.current_x2     = float(self._a_x2.text())
            pool.save()
            self.accept()
        except ValueError:
            pass  # keep dialog open so user can fix the bad value


class VC288Window(QWidget):
    def __init__(self, serial_terminal, parser=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("VC288 Sensor")
        self.setWindowFlag(Qt.WindowType.Window)
        self._st     = serial_terminal
        self._parser = parser
        self._initialized = False

        self._cfg = pool.section("vc288", defaults={
            "gpio": "GPIO13",
            "voltage_slope": 1.0, "voltage_offset": 0.0, "voltage_x2": 0.0,
            "current_slope": 1.0, "current_offset": 0.0, "current_x2": 0.0,
        })

        self._build_ui()

        serial_terminal.register_event_callback("0x60", self._on_voltage)
        serial_terminal.register_event_callback("0x61", self._on_current)
        serial_terminal.register_connection_state_callback(self._on_connection_changed)
        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Top bar ───────────────────────────────────────────────────
        bar = QHBoxLayout()

        bar.addWidget(QLabel("GPIO:"))
        self._gpio_combo = QtGPIOCombobox()
        self._gpio_combo.set_gpio(self._cfg.gpio)
        self._gpio_combo.setFixedWidth(100)
        bar.addWidget(self._gpio_combo)

        bar.addSpacing(8)

        self._init_btn = QPushButton("Init")
        self._init_btn.clicked.connect(self._do_init)
        bar.addWidget(self._init_btn)

        self._deinit_btn = QPushButton("Deinit")
        self._deinit_btn.clicked.connect(self._do_deinit)
        bar.addWidget(self._deinit_btn)

        bar.addSpacing(8)

        cfg_btn = QPushButton("Configure…")
        cfg_btn.clicked.connect(self._open_config)
        bar.addWidget(cfg_btn)

        bar.addStretch()
        root.addLayout(bar)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self._status_lbl)

        # ── Readings ──────────────────────────────────────────────────
        disp_box = QGroupBox("Sensor Readings")
        disp_lay = QVBoxLayout(disp_box)

        self._v_display = self._big_label("— V", "#FF6B6B")
        self._a_display = self._big_label("— A", "#4ECDC4")

        for caption, lbl in [("Voltage", self._v_display), ("Current", self._a_display)]:
            row = QHBoxLayout()
            cap = QLabel(f"{caption}:")
            cap.setFixedWidth(60)
            row.addWidget(cap)
            row.addWidget(lbl)
            disp_lay.addLayout(row)

        root.addWidget(disp_box)
        self.adjustSize()

    @staticmethod
    def _big_label(text: str, color: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setMinimumWidth(220)
        lbl.setStyleSheet(
            f"font-size: 28px; font-weight: bold; color: {color};"
            "background: #f0f0f0; border: 2px inset gray; padding: 4px;"
        )
        return lbl

    # ------------------------------------------------------------------
    def _send(self, cmd: str, callback=None) -> None:
        if self._parser is not None:
            self._parser.send(cmd, callback)
        elif self._st.serial.is_connected():
            self._st.send_command(cmd + "\n")

    def _do_init(self) -> None:
        gpio = self._gpio_combo.currentText()
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(msg)
            if status == "OK":
                self._initialized = True
                self._cfg.gpio = gpio
                pool.save()
                self._update_state()
        self._send(f"vc288 init {gpio}", on_resp)

    def _do_deinit(self) -> None:
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(msg)
            self._initialized = False
            self._v_display.setText("— V")
            self._a_display.setText("— A")
            self._update_state()
        self._send("vc288 deinit", on_resp)

    def _open_config(self) -> None:
        dlg = _ConfigDialog(self._cfg, self)
        dlg.exec()

    # ------------------------------------------------------------------
    def _on_voltage(self, timestamp: str, data: str) -> None:
        try:
            raw = float(data.strip())
            cal = (float(self._cfg.voltage_offset)
                   + float(self._cfg.voltage_slope) * raw
                   + float(self._cfg.voltage_x2) * raw ** 2)
            self._v_display.setText(f"{cal:.2f} V")
        except (ValueError, AttributeError):
            pass

    def _on_current(self, timestamp: str, data: str) -> None:
        try:
            raw = float(data.strip())
            cal = (float(self._cfg.current_offset)
                   + float(self._cfg.current_slope) * raw
                   + float(self._cfg.current_x2) * raw ** 2)
            self._a_display.setText(f"{cal:.3f} A")
        except (ValueError, AttributeError):
            pass

    # ------------------------------------------------------------------
    def _update_state(self) -> None:
        connected = self._st.serial.is_connected()
        self._gpio_combo.setEnabled(not self._initialized)
        self._init_btn.setEnabled(connected and not self._initialized)
        self._deinit_btn.setEnabled(connected and self._initialized)

    def _on_connection_changed(self) -> None:
        if not self._st.serial.is_connected():
            self._initialized = False
            self._v_display.setText("— V")
            self._a_display.setText("— A")
        self._update_state()

    def closeEvent(self, event) -> None:
        self._cfg.gpio = self._gpio_combo.currentText()
        pool.save()
        super().closeEvent(event)
