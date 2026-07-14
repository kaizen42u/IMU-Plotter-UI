"""Light control window (Qt port of apps/lightControlApp.py)."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from config_store import pool
from qt_spinbox import HSpinBox
from qt_throttled_slider import SliderDispatcher, ThrottledSlider


class _LightValuesDialog(QDialog):
    """Edit the ordered PWM-value sequence used by Array control mode."""

    def __init__(self, values: list[int], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Light Value Sequence")
        self._spins: list[HSpinBox] = []

        root = QVBoxLayout(self)
        root.addWidget(QLabel("Ordered PWM values (0–256) the slider steps through:"))
        self._rows_lay = QVBoxLayout()
        self._rows_lay.setSpacing(2)
        root.addLayout(self._rows_lay)

        for v in (values or [0]):
            self._add_row(v)

        add_btn = QPushButton("+ Add Value")
        add_btn.clicked.connect(lambda: self._add_row(self._spins[-1].value() if self._spins else 0))
        root.addWidget(add_btn)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

    def _add_row(self, value: int) -> None:
        row_w = QWidget()
        row = QHBoxLayout(row_w)
        row.setContentsMargins(0, 0, 0, 0)
        spin = HSpinBox()
        spin.setRange(0, 256)
        spin.setValue(int(value))
        spin.setFixedWidth(90)
        rm = QPushButton("−")
        rm.setFixedWidth(28)
        row.addWidget(spin)
        row.addWidget(rm)
        row.addStretch()
        self._rows_lay.addWidget(row_w)
        self._spins.append(spin)

        def remove():
            if len(self._spins) <= 1:
                return  # keep at least one value
            self._spins.remove(spin)
            row_w.setParent(None)
            row_w.deleteLater()
            self.adjustSize()
        rm.clicked.connect(remove)

    def values(self) -> list[int]:
        return [s.value() for s in self._spins]


class LightControlWindow(QWidget):
    GPIO_OPTIONS = [f"GPIO{i}" for i in range(22)] + [f"GPIO{i}" for i in range(26, 49)]
    FREQUENCY_OPTIONS = ["50Hz","60Hz","100Hz","120Hz","440Hz","1000Hz","10000Hz","44100Hz","48000Hz","96000Hz"]
    GAMMA_OPTIONS = [f"{round(x*0.1,1):.1f}" for x in range(10, 31)]

    def __init__(self, serial_terminal, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Light Control")
        self.serial_terminal = serial_terminal

        self._cfg = pool.section("light", defaults={
            "gpio": "GPIO14",
            "frequency": "44100Hz",
            "gamma": "2.3",
            "control_method": "gamma",
            "power_values": [0, 5, 15, 40, 80, 140, 200, 256],
            "bins": 64,
        })
        self._gpio = self._cfg.gpio
        self._freq = self._cfg.frequency
        self._gamma_str = self._cfg.gamma
        self._control_method = self._cfg.control_method
        self._power_values: list[int] = self._cfg.power_values
        # Gamma-mode slider resolution (number of steps); more = smoother output.
        self._bins = int(getattr(self._cfg, "bins", 64) or 64)
        self._initialized = False
        self._current_gamma = float(self._gamma_str)

        self._dispatcher = SliderDispatcher(serial_terminal)

        self._build_ui()
        serial_terminal.register_connection_state_callback(self._on_connection_changed)
        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        light_box = QGroupBox("LED Light")
        layout = QVBoxLayout(light_box)

        # Config row
        cfg_row = QHBoxLayout()
        cfg_row.addWidget(QLabel("GPIO:"))
        self._gpio_combo = QComboBox()
        self._gpio_combo.addItems(self.GPIO_OPTIONS)
        self._gpio_combo.setCurrentText(self._gpio)
        cfg_row.addWidget(self._gpio_combo)

        cfg_row.addWidget(QLabel("Frequency:"))
        self._freq_combo = QComboBox()
        self._freq_combo.addItems(self.FREQUENCY_OPTIONS)
        self._freq_combo.setCurrentText(self._freq)
        cfg_row.addWidget(self._freq_combo)

        cfg_row.addWidget(QLabel("Gamma:"))
        self._gamma_combo = QComboBox()
        self._gamma_combo.addItems(self.GAMMA_OPTIONS)
        self._gamma_combo.setCurrentText(self._gamma_str)
        self._gamma_combo.currentTextChanged.connect(self._on_gamma_changed)
        cfg_row.addWidget(self._gamma_combo)

        self._init_btn = QPushButton("Init")
        self._init_btn.clicked.connect(self._init_light)
        self._deinit_btn = QPushButton("Deinit")
        self._deinit_btn.clicked.connect(self._deinit_light)
        cfg_row.addWidget(self._init_btn)
        cfg_row.addWidget(self._deinit_btn)
        layout.addLayout(cfg_row)

        # Control method
        method_row = QHBoxLayout()
        method_row.addWidget(QLabel("Control Method:"))
        self._gamma_radio = QRadioButton("Gamma")
        self._array_radio = QRadioButton("Array")
        self._method_group = QButtonGroup()
        self._method_group.addButton(self._gamma_radio)
        self._method_group.addButton(self._array_radio)
        if self._control_method == "gamma":
            self._gamma_radio.setChecked(True)
        else:
            self._array_radio.setChecked(True)
        self._gamma_radio.toggled.connect(self._on_method_changed)
        method_row.addWidget(self._gamma_radio)
        method_row.addWidget(self._array_radio)

        method_row.addSpacing(10)
        method_row.addWidget(QLabel("Bins:"))
        self._bins_spin = HSpinBox()
        self._bins_spin.setRange(8, 256)
        self._bins_spin.setValue(self._bins)
        self._bins_spin.setToolTip("Gamma-mode slider resolution — more bins = smoother light")
        self._bins_spin.valueChanged.connect(self._on_bins_changed)
        method_row.addWidget(self._bins_spin)

        self._edit_values_btn = QPushButton("Edit Values…")
        self._edit_values_btn.setToolTip("Edit the Array-mode PWM value sequence")
        self._edit_values_btn.clicked.connect(self._show_values_editor)
        method_row.addWidget(self._edit_values_btn)

        method_row.addStretch()
        layout.addLayout(method_row)

        # Power slider
        power_row = QHBoxLayout()
        power_row.addWidget(QLabel("Power Level:"))
        self._power_slider = ThrottledSlider(
            self._dispatcher,
            command_fn=lambda v: f"light fadeto {self._level_to_pwm(v)} 3 {self._current_gamma:g}",
            label_fn=lambda v: f"{self._level_to_pwm(v)}/256",
            label_width=60,
        )
        self._power_slider.setEnabled(False)
        self._power_slider.set_label_style("background: #90EE90; border: 1px inset gray;")
        power_row.addWidget(self._power_slider, stretch=1)
        layout.addLayout(power_row)
        self._apply_slider_range()

        root.addWidget(light_box)
        root.addStretch()
        self.setFixedSize(self.sizeHint())

    # ------------------------------------------------------------------
    def _level_to_pwm(self, level: int) -> int:
        if self._control_method == "array":
            level = max(0, min(level, len(self._power_values) - 1))
            return self._power_values[level]
        steps = max(self._power_slider.maximum(), 1)
        normalized = level / steps
        return int(pow(normalized, self._current_gamma) * 256)

    def _on_gamma_changed(self, text: str) -> None:
        try:
            self._current_gamma = float(text)
        except ValueError:
            pass

    def _apply_slider_range(self) -> None:
        # Gamma mode uses the configurable bin count for smoothness; Array mode
        # is naturally limited to the number of values in the sequence.
        if self._control_method == "gamma":
            hi = max(1, self._bins - 1)
        else:
            hi = max(1, len(self._power_values) - 1)
        cur = min(self._power_slider.value(), hi)
        self._power_slider.setRange(0, hi)
        self._power_slider.set_value_silent(cur)

    def _on_bins_changed(self, value: int) -> None:
        self._bins = value
        if self._control_method == "gamma":
            self._apply_slider_range()

    def _show_values_editor(self) -> None:
        dlg = _LightValuesDialog(self._power_values, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            vals = dlg.values()
            if vals:
                self._power_values = vals
                self._cfg.power_values = vals
                pool.save()
                if self._control_method == "array":
                    self._apply_slider_range()

    def _on_method_changed(self) -> None:
        self._control_method = "gamma" if self._gamma_radio.isChecked() else "array"
        self._gamma_combo.setEnabled(self._control_method == "gamma" and not self._initialized)
        self._bins_spin.setEnabled(self._control_method == "gamma")
        self._apply_slider_range()

    def _init_light(self) -> None:
        gpio_str = self._gpio_combo.currentText()
        gpio_num = int(gpio_str.replace("GPIO", ""))
        freq_num = self._freq_combo.currentText().replace("Hz", "")
        self._send_command(f"light config {gpio_num} {freq_num}")
        self._send_command(f"light freq {freq_num}")
        self._initialized = True
        self._update_state()

    def _deinit_light(self) -> None:
        self._send_command("light set 0")
        self._send_command("light delete")
        self._initialized = False
        self._power_slider.set_value_silent(0)
        self._update_state()

    def _update_state(self) -> None:
        connected = self.serial_terminal.serial.is_connected()
        # Buttons are managed here too — Init/Deinit change _initialized and call
        # _update_state(), so leaving the button enables out of it (as before) left
        # Deinit permanently disabled after Init.
        self._init_btn.setEnabled(connected and not self._initialized)
        self._deinit_btn.setEnabled(connected and self._initialized)
        self._gpio_combo.setEnabled(not self._initialized)
        self._freq_combo.setEnabled(not self._initialized)
        self._gamma_combo.setEnabled(not self._initialized and self._control_method == "gamma")
        self._power_slider.setEnabled(connected and self._initialized)

    def _on_connection_changed(self) -> None:
        if not self.serial_terminal.serial.is_connected():
            self._initialized = False   # firmware lost the light config
        self._update_state()

    def increase_power(self) -> None:
        if self._initialized:
            val = self._power_slider.value()
            if val < self._power_slider.maximum():
                self._power_slider.setValue(val + 1)

    def decrease_power(self) -> None:
        if self._initialized:
            val = self._power_slider.value()
            if val > 0:
                self._power_slider.setValue(val - 1)

    def _send_command(self, command: str) -> None:
        if not command.endswith("\n"):
            command += "\n"
        if self.serial_terminal.serial.is_connected():
            self.serial_terminal.send_command(command)

    def reload_from_config(self) -> None:
        """Re-read cfg values and update UI after a profile switch."""
        self._gpio = self._cfg.gpio
        self._freq = self._cfg.frequency
        self._gamma_str = self._cfg.gamma
        self._control_method = self._cfg.control_method
        self._power_values = self._cfg.power_values
        self._bins = int(getattr(self._cfg, "bins", 64) or 64)
        self._current_gamma = float(self._gamma_str)

        self._gpio_combo.setCurrentText(self._gpio)
        self._freq_combo.setCurrentText(self._freq)
        self._gamma_combo.setCurrentText(self._gamma_str)
        self._bins_spin.setValue(self._bins)
        if self._control_method == "gamma":
            self._gamma_radio.setChecked(True)
        else:
            self._array_radio.setChecked(True)
        self._apply_slider_range()
        self._power_slider.set_value_silent(0)

    def _save_config(self) -> None:
        self._cfg.gpio = self._gpio_combo.currentText()
        self._cfg.frequency = self._freq_combo.currentText()
        self._cfg.gamma = self._gamma_combo.currentText()
        self._cfg.control_method = self._control_method
        self._cfg.power_values = self._power_values
        self._cfg.bins = self._bins
        pool.save()

    def closeEvent(self, event) -> None:
        self._save_config()
        super().closeEvent(event)
