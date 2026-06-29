"""VC288 voltage/current sensor window (Qt port of apps/vc288App.py)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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


class VC288Window(QWidget):
    def __init__(self, serial_terminal, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("VC288 Sensor")
        self.serial_terminal = serial_terminal

        self._cfg = pool.section("vc288", defaults={
            "gpio": "GPIO13",
            "voltage_slope": 1.0, "voltage_offset": 0.0, "voltage_x2": 0.0,
            "current_slope": 1.0, "current_offset": 0.0, "current_x2": 0.0,
        })
        self._v_slope: float = self._cfg.voltage_slope
        self._v_offset: float = self._cfg.voltage_offset
        self._v_x2: float = self._cfg.voltage_x2
        self._a_slope: float = self._cfg.current_slope
        self._a_offset: float = self._cfg.current_offset
        self._a_x2: float = self._cfg.current_x2
        self._initialized = False

        serial_terminal.register_event_callback("0x60", self._on_voltage)
        serial_terminal.register_event_callback("0x61", self._on_current)
        serial_terminal.register_connection_state_callback(self._on_connection_changed)

        self._build_ui()
        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # Config section
        cfg_box = QGroupBox("Configuration")
        cfg_layout = QHBoxLayout(cfg_box)

        cfg_layout.addWidget(QLabel("GPIO:"))
        self._gpio_combo = QtGPIOCombobox()
        self._gpio_combo.set_gpio(self._cfg.gpio)
        cfg_layout.addWidget(self._gpio_combo)

        def _add_field(layout, label, value, attr, width=10):
            layout.addWidget(QLabel(label))
            entry = QLineEdit(f"{value:.6f}")
            entry.setFixedWidth(width * 8)
            entry.returnPressed.connect(self._save_config)
            setattr(self, attr, entry)
            layout.addWidget(entry)

        _add_field(cfg_layout, "V Slope:", self._v_slope, "_v_slope_entry")
        _add_field(cfg_layout, "V Offset:", self._v_offset, "_v_offset_entry")
        _add_field(cfg_layout, "V X2:", self._v_x2, "_v_x2_entry", 12)
        _add_field(cfg_layout, "A Slope:", self._a_slope, "_a_slope_entry")
        _add_field(cfg_layout, "A Offset:", self._a_offset, "_a_offset_entry")
        _add_field(cfg_layout, "A X2:", self._a_x2, "_a_x2_entry", 12)

        self._init_btn = QPushButton("Init")
        self._init_btn.clicked.connect(self._init_sensor)
        self._deinit_btn = QPushButton("Deinit")
        self._deinit_btn.clicked.connect(self._deinit_sensor)
        cfg_layout.addWidget(self._init_btn)
        cfg_layout.addWidget(self._deinit_btn)
        root.addWidget(cfg_box)

        # Display section
        disp_box = QGroupBox("Sensor Readings")
        disp_layout = QVBoxLayout(disp_box)

        v_row = QHBoxLayout()
        v_row.addWidget(QLabel("Voltage:"))
        self._v_display = QLabel("0.00 V")
        self._v_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._v_display.setStyleSheet("font-size: 28px; font-weight: bold; color: #FF6B6B; background: #F0F0F0; border: 2px inset gray;")
        self._v_display.setMinimumWidth(200)
        v_row.addWidget(self._v_display)
        disp_layout.addLayout(v_row)

        a_row = QHBoxLayout()
        a_row.addWidget(QLabel("Current:"))
        self._a_display = QLabel("0.000 A")
        self._a_display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._a_display.setStyleSheet("font-size: 28px; font-weight: bold; color: #4ECDC4; background: #F0F0F0; border: 2px inset gray;")
        self._a_display.setMinimumWidth(200)
        a_row.addWidget(self._a_display)
        disp_layout.addLayout(a_row)

        root.addWidget(disp_box)
        self.setMinimumWidth(700)

    # ------------------------------------------------------------------
    def _on_voltage(self, timestamp: str, data: str) -> None:
        try:
            raw = float(data.strip())
            self._read_calib()
            cal = self._v_offset + self._v_slope * raw + self._v_x2 * raw ** 2
            self._v_display.setText(f"{cal:.2f} V")
        except ValueError:
            pass

    def _on_current(self, timestamp: str, data: str) -> None:
        try:
            raw = float(data.strip())
            self._read_calib()
            cal = self._a_offset + self._a_slope * raw + self._a_x2 * raw ** 2
            self._a_display.setText(f"{cal:.3f} A")
        except ValueError:
            pass

    def _read_calib(self) -> None:
        try:
            self._v_slope = float(self._v_slope_entry.text())
            self._v_offset = float(self._v_offset_entry.text())
            self._v_x2 = float(self._v_x2_entry.text())
            self._a_slope = float(self._a_slope_entry.text())
            self._a_offset = float(self._a_offset_entry.text())
            self._a_x2 = float(self._a_x2_entry.text())
        except ValueError:
            pass

    def _init_sensor(self) -> None:
        gpio = self._gpio_combo.currentText()
        self.serial_terminal.send_command(f"vc288 init {gpio}\n")
        self._initialized = True
        self._save_config()
        self._update_state()
        self._on_connection_changed()

    def _deinit_sensor(self) -> None:
        self.serial_terminal.send_command("vc288 deinit\n")
        self._initialized = False
        self._v_display.setText("0.00 V")
        self._a_display.setText("0.000 A")
        self._update_state()
        self._on_connection_changed()

    def _update_state(self) -> None:
        self._gpio_combo.setEnabled(not self._initialized)
        self._init_btn.setEnabled(not self._initialized)
        self._deinit_btn.setEnabled(self._initialized)

    def _on_connection_changed(self) -> None:
        connected = self.serial_terminal.serial.is_connected()
        self._init_btn.setEnabled(connected and not self._initialized)
        self._deinit_btn.setEnabled(connected and self._initialized)

    def _save_config(self) -> None:
        self._read_calib()
        self._cfg.gpio = self._gpio_combo.currentText()
        self._cfg.voltage_slope = self._v_slope
        self._cfg.voltage_offset = self._v_offset
        self._cfg.voltage_x2 = self._v_x2
        self._cfg.current_slope = self._a_slope
        self._cfg.current_offset = self._a_offset
        self._cfg.current_x2 = self._a_x2
        pool.save()

    def closeEvent(self, event) -> None:
        self._save_config()
        super().closeEvent(event)
