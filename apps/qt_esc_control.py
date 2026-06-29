"""ESC control window (Qt port of apps/escControlApp.py)."""

from typing import cast

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from config_store import pool
from qt_gpio_combobox import QtGPIOCombobox
from qt_throttled_slider import SliderDispatcher, ThrottledSlider


class ESCControlWindow(QWidget):
    FREQUENCY_OPTIONS = ["50Hz", "100Hz", "200Hz", "300Hz"]
    DIRECTION_OPTIONS = ["Normal", "Inverted"]

    def __init__(self, serial_terminal, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ESC Control")
        self.serial_terminal = serial_terminal

        self._cfg = pool.section("esc", defaults={
            "num_of_esc": 4,
            "frequency": "300Hz",
        })
        self._num_escs: int = self._cfg.num_of_esc
        self._esc_freq: str = self._cfg.frequency

        self._esc_configs = []
        for i in range(1, self._num_escs + 1):
            saved = getattr(self._cfg, f"esc{i}", None)
            if saved:
                self._esc_configs.append(saved)
            else:
                self._esc_configs.append({"gpio": f"{8 + i}", "direction": "Normal",
                                          "calibration": [1000, 1500, 1500, 1500, 2000], "selected": True})

        self._gpio_combos: list[QtGPIOCombobox | None] = [None] * self._num_escs
        self._dir_combos: list[QComboBox | None] = [None] * self._num_escs
        self._calib_entries: list[list[QLineEdit]] = []
        self._sliders: list[ThrottledSlider] = []
        self._selected: list[QCheckBox] = []
        self._initialized: list[bool] = [False] * self._num_escs

        self._dispatcher = SliderDispatcher(serial_terminal)

        self._build_ui()
        serial_terminal.register_connection_state_callback(self._on_connection_changed)
        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_area.setWidget(scroll_widget)

        common = QGroupBox("Common Settings")
        common_layout = QHBoxLayout(common)
        common_layout.addWidget(QLabel("Frequency:"))
        self._freq_combo = QComboBox()
        self._freq_combo.addItems(self.FREQUENCY_OPTIONS)
        self._freq_combo.setCurrentText(self._esc_freq)
        common_layout.addWidget(self._freq_combo)
        common_layout.addStretch()
        self._init_all_btn = QPushButton("Init ESCs")
        self._init_all_btn.clicked.connect(self._init_escs)
        self._deinit_all_btn = QPushButton("Deinit ESCs")
        self._deinit_all_btn.clicked.connect(self._deinit_escs)
        common_layout.addWidget(self._init_all_btn)
        common_layout.addWidget(self._deinit_all_btn)
        scroll_layout.addWidget(common)

        for i in range(self._num_escs):
            scroll_layout.addWidget(self._make_esc_section(i))

        scroll_layout.addStretch()
        outer.addWidget(scroll_area)
        self.setMinimumSize(700, 500)

    def _make_esc_section(self, index: int) -> QGroupBox:
        box = QGroupBox(f"ESC {index + 1}")
        layout = QVBoxLayout(box)

        # Config row
        cfg_row = QHBoxLayout()
        cfg_row.addWidget(QLabel("GPIO:"))
        gpio_combo = QtGPIOCombobox()
        gpio_val = self._esc_configs[index].get("gpio", f"GPIO{9 + index}")
        gpio_combo.set_gpio(str(gpio_val) if not str(gpio_val).startswith("G") else gpio_val)
        cfg_row.addWidget(gpio_combo)
        self._gpio_combos[index] = gpio_combo

        cfg_row.addWidget(QLabel("Direction:"))
        dir_combo = QComboBox()
        dir_combo.addItems(self.DIRECTION_OPTIONS)
        dir_combo.setCurrentText(self._esc_configs[index].get("direction", "Normal"))
        cfg_row.addWidget(dir_combo)
        self._dir_combos[index] = dir_combo

        sel_cb = QCheckBox("Selected")
        sel_cb.setChecked(self._esc_configs[index].get("selected", True))
        sel_cb.toggled.connect(self._on_connection_changed)
        cfg_row.addWidget(sel_cb)
        self._selected.append(sel_cb)

        layout.addLayout(cfg_row)

        # Calibration row
        calib_row = QHBoxLayout()
        calib_row.addWidget(QLabel("Calibrations:"))
        labels = ["BW Max", "BW Min", "Idle", "FW Min", "FW Max"]
        defaults = self._esc_configs[index].get("calibration", [1000, 1500, 1500, 1500, 2000])
        entries: list[QLineEdit] = []
        for lbl, val in zip(labels, defaults):
            calib_row.addWidget(QLabel(f"{lbl}:"))
            entry = QLineEdit(str(val))
            entry.setFixedWidth(55)
            calib_row.addWidget(entry)
            entries.append(entry)
        self._calib_entries.append(entries)
        layout.addLayout(calib_row)

        # Power slider row
        power_row = QHBoxLayout()
        power_row.addWidget(QLabel("Motor Power:"))
        slider = ThrottledSlider(
            self._dispatcher,
            command_fn=lambda v, idx=index: f"esc {idx + 1} pw {v / 100:.2f}",
            label_fn=lambda v: f"{v / 100:.2f}",
            label_width=50,
        )
        slider.setRange(-100, 100)
        slider.setEnabled(False)
        slider.set_label_style("background: #90EE90; border: 1px inset gray;")
        slider.valueChanged.connect(lambda v, s=slider: self._update_power_style(s, v))
        self._sliders.append(slider)
        power_row.addWidget(slider, stretch=1)
        layout.addLayout(power_row)

        return box

    # ------------------------------------------------------------------
    def _update_power_style(self, slider: ThrottledSlider, val: int) -> None:
        if val == 0:
            slider.set_label_style("background: #90EE90; border: 1px inset gray;")
        elif val > 0:
            slider.set_label_style("background: #FFFF00; border: 1px inset gray;")
        else:
            slider.set_label_style("background: #FFA500; border: 1px inset gray;")

    def _init_escs(self) -> None:
        delay = 0
        for i in range(self._num_escs):
            if not self._selected[i].isChecked() or self._initialized[i]:
                continue
            gpio = self._gpio_combos[i]
            if gpio is None:
                continue
            gpio_str = str(gpio.get_gpio() or "")
            dir_str = cast(QComboBox, self._dir_combos[i]).currentText()
            dir_num = 0 if dir_str == "Normal" else 1
            try:
                calib = [int(e.text()) for e in self._calib_entries[i]]
            except ValueError:
                calib = [1000, 1500, 1500, 1500, 2000]
            freq_num = self._freq_combo.currentText().replace("Hz", "")

            QTimer.singleShot(delay, lambda fn=freq_num: self._send_command(f"esc freq {fn}"))
            delay += 200
            QTimer.singleShot(delay, lambda cmd=f"esc {i+1} init {gpio_str}", idx=i: self._on_init_sent(cmd, idx))
            delay += 200
            QTimer.singleShot(delay, lambda di=dir_num, ii=i+1: self._send_command(f"esc {ii} dir {di}"))
            delay += 200
            cv = " ".join(str(v) for v in calib)
            QTimer.singleShot(delay, lambda ii=i+1, c=cv: self._send_command(f"esc {ii} cali {c}"))
            delay += 200
            for pwr in [0.00, -0.01, 0.00, 0.01, 0.00]:
                QTimer.singleShot(delay, lambda ii=i+1, p=pwr: self._send_command(f"esc {ii} pw {p:.2f}"))
                delay += 750

    def _on_init_sent(self, command: str, index: int) -> None:
        self._send_command(command)
        self._initialized[index] = True
        self._sliders[index].set_value_silent(0)
        self._update_esc_state(index)
        self._on_connection_changed()

    def _deinit_escs(self) -> None:
        delay = 0
        for i in range(self._num_escs):
            if not self._selected[i].isChecked() or not self._initialized[i]:
                continue
            QTimer.singleShot(delay, lambda ii=i: self._on_deinit_sent(ii))
            delay += 200

    def _on_deinit_sent(self, index: int) -> None:
        self._send_command(f"esc {index+1} deinit")
        self._initialized[index] = False
        self._sliders[index].set_value_silent(0)
        self._sliders[index].set_label_style("background: #90EE90; border: 1px inset gray;")
        self._update_esc_state(index)
        self._on_connection_changed()

    def _update_esc_state(self, index: int) -> None:
        init = self._initialized[index]
        if self._gpio_combos[index]:
            self._gpio_combos[index].setEnabled(not init)
        if self._dir_combos[index]:
            self._dir_combos[index].setEnabled(not init)
        for e in self._calib_entries[index]:
            e.setEnabled(not init)
        self._sliders[index].setEnabled(init)
        self._freq_combo.setEnabled(not any(self._initialized))

    def _on_connection_changed(self) -> None:
        connected = self.serial_terminal.serial.is_connected()
        selected = [i for i in range(self._num_escs) if self._selected[i].isChecked()]
        has_uninit = any(not self._initialized[i] for i in selected)
        has_init = any(self._initialized[i] for i in selected)
        self._init_all_btn.setEnabled(connected and has_uninit)
        self._deinit_all_btn.setEnabled(connected and has_init)

    def send_all_esc_power(self, power_levels: list[float]) -> None:
        """Set power on all ESCs immediately (bypasses dispatcher for real-time control)."""
        power_levels = power_levels[:self._num_escs]
        for i, pwr in enumerate(power_levels):
            if i < len(self._sliders):
                ival = int(pwr * 100)
                self._sliders[i].set_value_silent(ival)
                self._update_power_style(self._sliders[i], ival)
            if self._initialized[i]:
                self._send_command(f"esc {i+1} pw {pwr:.2f}")

    def stop_all_escs(self) -> None:
        self.send_all_esc_power([0.0] * self._num_escs)

    @property
    def num_escs(self) -> int:
        return self._num_escs

    def _send_command(self, command: str) -> None:
        if not command.endswith("\n"):
            command += "\n"
        if self.serial_terminal.serial.is_connected():
            self.serial_terminal.send_command(command)

    def _save_config(self) -> None:
        self._cfg.frequency = self._freq_combo.currentText()
        self._cfg.num_of_esc = self._num_escs
        for i in range(self._num_escs):
            gpio = self._gpio_combos[i]
            gpio_val = str(gpio.get_gpio()) if gpio else self._esc_configs[i].get("gpio", "")
            dir_val = cast(QComboBox, self._dir_combos[i]).currentText() if self._dir_combos[i] else "Normal"
            try:
                calib = [int(e.text()) for e in self._calib_entries[i]]
            except ValueError:
                calib = [1000, 1500, 1500, 1500, 2000]
            selected = self._selected[i].isChecked() if i < len(self._selected) else True
            setattr(self._cfg, f"esc{i+1}", {
                "gpio": gpio_val, "direction": dir_val,
                "calibration": calib, "selected": selected,
            })
        pool.save()

    def closeEvent(self, event) -> None:
        self._save_config()
        super().closeEvent(event)
