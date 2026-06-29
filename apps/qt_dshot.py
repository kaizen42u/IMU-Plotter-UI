"""DShot ESC control window."""

from config_store import pool

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from qt_throttled_slider import SliderDispatcher, ThrottledSlider

_GPIO_OPTIONS = [f"GPIO{i}" for i in range(22)] + [f"GPIO{i}" for i in range(26, 49)]
_RATES = ["150", "300", "600", "1200"]
_MAX_DEVICES = 8


class _DeviceWidget(QGroupBox):
    """UI panel for a single DShot device."""

    def __init__(
        self,
        device_id: int,
        serial_terminal,
        dispatcher: SliderDispatcher,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(f"DShot {device_id}", parent)
        self._id = device_id
        self._st = serial_terminal
        self._initialized = False
        self._build_ui(dispatcher)
        self._update_state()

    # ------------------------------------------------------------------
    def _build_ui(self, dispatcher: SliderDispatcher) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ── Config row ────────────────────────────────────────────────
        cfg = QHBoxLayout()

        cfg.addWidget(QLabel("GPIO:"))
        self._gpio_combo = QComboBox()
        self._gpio_combo.addItems(_GPIO_OPTIONS)
        self._gpio_combo.setCurrentText("GPIO14")
        self._gpio_combo.setFixedWidth(90)
        cfg.addWidget(self._gpio_combo)

        cfg.addWidget(QLabel("Rate:"))
        self._rate_combo = QComboBox()
        self._rate_combo.addItems(_RATES)
        self._rate_combo.setCurrentText("600")
        self._rate_combo.setFixedWidth(70)
        self._rate_combo.currentTextChanged.connect(self._on_rate_changed)
        cfg.addWidget(self._rate_combo)

        self._bidi_cb = QCheckBox("BiDi (not yet supported)")
        self._bidi_cb.setEnabled(False)
        cfg.addWidget(self._bidi_cb)

        self._dir_cb = QCheckBox("Inverted")
        self._dir_cb.toggled.connect(self._on_dir_changed)
        cfg.addWidget(self._dir_cb)

        cfg.addStretch()

        self._init_btn = QPushButton("Init")
        self._init_btn.clicked.connect(self._do_init)
        self._deinit_btn = QPushButton("Deinit")
        self._deinit_btn.clicked.connect(self._do_deinit)
        cfg.addWidget(self._init_btn)
        cfg.addWidget(self._deinit_btn)

        root.addLayout(cfg)

        # ── Power slider (-1.0 … 1.0) ────────────────────────────────
        power_row = QHBoxLayout()
        power_row.addWidget(QLabel("Power:"))
        self._power_slider = ThrottledSlider(
            dispatcher,
            command_fn=lambda v: f"dshot {self._id} set {v / 100:.3f}",
            label_fn=lambda v: f"{v / 100:.2f}",
            label_width=40,
        )
        self._power_slider.setRange(-100, 100)
        power_row.addWidget(self._power_slider, stretch=1)
        root.addLayout(power_row)

    # ------------------------------------------------------------------
    def _cmd(self, *args) -> None:
        if self._st.serial.is_connected():
            self._st.send_command(f"dshot {self._id} " + " ".join(str(a) for a in args) + "\n")

    def _do_init(self) -> None:
        gpio = self._gpio_combo.currentText().replace("GPIO", "")
        self._cmd("init", gpio, self._rate_combo.currentText())
        self._initialized = True
        self._update_state()

    def _do_deinit(self) -> None:
        self._cmd("deinit")
        self._initialized = False
        self._power_slider.set_value_silent(0)
        self._update_state()

    def _on_rate_changed(self, rate: str) -> None:
        if self._initialized:
            self._cmd("rate", rate)

    def _on_dir_changed(self, checked: bool) -> None:
        if self._initialized:
            self._cmd("dir", 1 if checked else 0)

    def on_connection_changed(self) -> None:
        if not self._st.serial.is_connected():
            self._initialized = False
            self._power_slider.set_value_silent(0)
        self._update_state()

    def _update_state(self) -> None:
        connected = self._st.serial.is_connected()
        self._init_btn.setEnabled(connected and not self._initialized)
        self._deinit_btn.setEnabled(connected and self._initialized)
        self._gpio_combo.setEnabled(not self._initialized)
        self._power_slider.setEnabled(self._initialized)

    def get_saved_state(self) -> dict:
        return {
            "gpio": self._gpio_combo.currentText(),
            "rate": self._rate_combo.currentText(),
            "inverted": self._dir_cb.isChecked(),
        }

    def apply_saved_state(self, state: dict) -> None:
        if "gpio" in state:
            self._gpio_combo.setCurrentText(state["gpio"])
        if "rate" in state:
            self._rate_combo.setCurrentText(state["rate"])
        if "inverted" in state:
            self._dir_cb.setChecked(state["inverted"])


# ---------------------------------------------------------------------------

class DShotWindow(QWidget):
    """DShot control panel — supports up to 8 independent DShot devices."""

    def __init__(self, serial_terminal, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("DShot Control")
        self.setWindowFlag(Qt.WindowType.Window)
        self._st = serial_terminal
        self._devices: list[_DeviceWidget] = []
        self._dispatcher = SliderDispatcher(serial_terminal)

        self._build_ui()
        serial_terminal.register_connection_state_callback(self._on_connection_changed)

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        self._device_layout = QVBoxLayout()
        self._device_layout.setSpacing(6)
        root.addLayout(self._device_layout)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("+ Add Device")
        self._add_btn.clicked.connect(self._add_device)
        self._remove_btn = QPushButton("− Remove Last")
        self._remove_btn.clicked.connect(self._remove_device)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._remove_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

        self._add_device()
        self._update_buttons()

    # ------------------------------------------------------------------
    def _add_device(self) -> None:
        if len(self._devices) >= _MAX_DEVICES:
            return
        dev = _DeviceWidget(len(self._devices) + 1, self._st, self._dispatcher)
        self._devices.append(dev)
        self._device_layout.addWidget(dev)
        self._update_buttons()
        self.adjustSize()

    def _remove_device(self) -> None:
        if not self._devices:
            return
        dev = self._devices.pop()
        self._device_layout.removeWidget(dev)
        dev.deleteLater()
        self._update_buttons()
        self.adjustSize()

    def _update_buttons(self) -> None:
        self._add_btn.setEnabled(len(self._devices) < _MAX_DEVICES)
        self._remove_btn.setEnabled(len(self._devices) > 0)

    def _on_connection_changed(self) -> None:
        for dev in self._devices:
            dev.on_connection_changed()

    # ------------------------------------------------------------------
    def _save_config(self) -> None:
        cfg = pool.section("dshot")
        cfg.num_devices = len(self._devices)
        for i, dev in enumerate(self._devices):
            setattr(cfg, f"device{i + 1}", dev.get_saved_state())
        pool.save()

    def reload_from_config(self) -> None:
        cfg = pool.section("dshot")
        num = cfg.num_devices or len(self._devices)

        while len(self._devices) > num:
            self._remove_device()
        while len(self._devices) < num:
            self._add_device()

        for i, dev in enumerate(self._devices):
            saved = getattr(cfg, f"device{i + 1}", {}) or {}
            dev.apply_saved_state({
                "gpio": saved.get("gpio", dev._gpio_combo.currentText()),
                "rate": saved.get("rate", dev._rate_combo.currentText()),
                "inverted": saved.get("inverted", dev._dir_cb.isChecked()),
            })

    def closeEvent(self, event) -> None:
        self._save_config()
        super().closeEvent(event)
