"""Bidirectional DShot (bDShot) control pane — throttle + live eRPM telemetry.

Firmware: bdshot <id> [init|deinit|rate|dir|set|send|hz|stop|erpm|raw]  (id 1-4)
  init <gpio> [rate]   → start bidi DShot, idle stream running
  dir <0|1>            → set spin direction (0 normal, 1 inverted)
  set <-1.0..1.0>      → throttle (normalized; negative = reverse in bidi)

eRPM is delivered by a single event for all devices:
  0x80 EVENT_BDSHOT_ERPM,  data "<device_id> <erpm>"
"""

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

from config_store import pool
from qt_throttled_slider import SliderDispatcher, ThrottledSlider

_GPIO_OPTIONS = [f"GPIO{i}" for i in range(22)] + [f"GPIO{i}" for i in range(26, 49)]
# 1200 dropped for now — MCU can't keep up with eRPM replies at that rate.
_RATES = ["150", "300", "600"]
_MAX_DEVICES = 4

# Single eRPM event for all devices; payload carries the device id.
_ERPM_EVENT = "0x80"


class _BDShotDevice(QGroupBox):
    """One bidirectional-DShot device: config + throttle + eRPM readout."""

    def __init__(self, device_id, serial_terminal, dispatcher, parent=None) -> None:
        super().__init__(f"bDShot {device_id}", parent)
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
        cfg.addWidget(self._rate_combo)

        self._bidi_cb = QCheckBox("BiDi (reversible)")
        self._bidi_cb.setToolTip("Reversible throttle — slider spans reverse…forward")
        self._bidi_cb.toggled.connect(self._on_bidi_changed)
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

        # ── Throttle + live eRPM ─────────────────────────────────────
        power_row = QHBoxLayout()
        power_row.addWidget(QLabel("Throttle:"))
        self._power_slider = ThrottledSlider(
            dispatcher,
            command_fn=lambda v: f"bdshot {self._id} set {v / 100:.3f}",
            label_fn=lambda v: f"{v}%",
            label_width=40,
        )
        # Reverse (negative) half only exists in bidirectional mode.
        self._power_slider.setRange(-100 if self._bidi_cb.isChecked() else 0, 100)
        power_row.addWidget(self._power_slider, stretch=1)

        power_row.addSpacing(10)
        power_row.addWidget(QLabel("eRPM:"))
        self._erpm_lbl = QLabel("—")
        self._erpm_lbl.setStyleSheet("font-weight:bold; font-size:14px;")
        self._erpm_lbl.setMinimumWidth(64)
        self._erpm_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        power_row.addWidget(self._erpm_lbl)
        root.addLayout(power_row)

    # ------------------------------------------------------------------
    def _cmd(self, *args) -> None:
        if self._st.serial.is_connected():
            self._st.send_command(f"bdshot {self._id} " + " ".join(str(a) for a in args) + "\n")

    def _do_init(self) -> None:
        gpio = self._gpio_combo.currentText().replace("GPIO", "")
        self._cmd("init", gpio, self._rate_combo.currentText())
        self._initialized = True
        # Apply the saved direction to the freshly-inited ESC.
        self._cmd("dir", 1 if self._dir_cb.isChecked() else 0)
        self._update_state()

    def _do_deinit(self) -> None:
        self._cmd("deinit")
        self._initialized = False
        self._power_slider.set_value_silent(0)
        self._erpm_lbl.setText("—")
        self._update_state()

    def _on_dir_changed(self, checked: bool) -> None:
        if self._initialized:
            self._cmd("dir", 1 if checked else 0)

    def _on_bidi_changed(self, checked: bool) -> None:
        # Give the slider the reverse half in bidi mode; drop to stop so switching
        # modes can't leave a stale reverse setpoint applied. bDShot reverses via
        # a negative `set` value (no separate firmware bidi command).
        self._power_slider.setRange(-100 if checked else 0, 100)
        self._power_slider.set_value_silent(0)
        if self._initialized:
            self._cmd("set", "0.000")

    def set_erpm(self, value) -> None:
        self._erpm_lbl.setText(str(value))

    # ------------------------------------------------------------------
    def on_connection_changed(self) -> None:
        if not self._st.serial.is_connected():
            self._initialized = False
            self._power_slider.set_value_silent(0)
            self._erpm_lbl.setText("—")
        self._update_state()

    def _update_state(self) -> None:
        connected = self._st.serial.is_connected()
        self._init_btn.setEnabled(connected and not self._initialized)
        self._deinit_btn.setEnabled(connected and self._initialized)
        self._gpio_combo.setEnabled(not self._initialized)
        self._rate_combo.setEnabled(not self._initialized)
        self._power_slider.setEnabled(self._initialized)

    def get_saved_state(self) -> dict:
        return {
            "gpio": self._gpio_combo.currentText(),
            "rate": self._rate_combo.currentText(),
            "bidi": self._bidi_cb.isChecked(),
            "inverted": self._dir_cb.isChecked(),
        }

    def apply_saved_state(self, state: dict) -> None:
        if "gpio" in state:
            self._gpio_combo.setCurrentText(state["gpio"])
        if "rate" in state:
            self._rate_combo.setCurrentText(state["rate"])
        if "bidi" in state:
            self._bidi_cb.setChecked(state["bidi"])
        if "inverted" in state:
            self._dir_cb.setChecked(state["inverted"])


# ---------------------------------------------------------------------------

class BDShotWindow(QWidget):
    """Bidirectional DShot control — up to 4 devices with event-driven eRPM."""

    def __init__(self, serial_terminal, parser=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("bDShot Control")
        self.setWindowFlag(Qt.WindowType.Window)
        self._st = serial_terminal
        self._parser = parser
        self._devices: list[_BDShotDevice] = []
        self._dispatcher = SliderDispatcher(serial_terminal)

        self._build_ui()
        self.reload_from_config()

        # eRPM arrives via a single event (0x80) carrying "<device_id> <erpm>";
        # registering also enables it on the firmware.
        serial_terminal.register_event_callback(_ERPM_EVENT, self._on_erpm_event)
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
        dev = _BDShotDevice(len(self._devices) + 1, self._st, self._dispatcher)
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

    def _on_erpm_event(self, timestamp: str, data: str) -> None:
        # data: "<device_id> <erpm>" — route to the device with the matching id.
        parts = data.split()
        if len(parts) < 2:
            return
        try:
            dev_id = int(parts[0])
        except ValueError:
            return
        for dev in self._devices:
            if dev._id == dev_id:
                dev.set_erpm(parts[1])
                break

    def _on_connection_changed(self) -> None:
        for dev in self._devices:
            dev.on_connection_changed()

    # ------------------------------------------------------------------
    # Public API — used by the control pad (mirrors DShotWindow).
    # ------------------------------------------------------------------

    @property
    def num_escs(self) -> int:
        return len(self._devices)

    def send_all_esc_power(self, power_levels: list[float]) -> None:
        for i, pwr in enumerate(power_levels[: len(self._devices)]):
            dev = self._devices[i]
            dev._power_slider.set_value_silent(int(round(pwr * 100)))
            if dev._initialized and self._st.serial.is_connected():
                self._st.send_command(f"bdshot {dev._id} set {pwr:.3f}\n")

    def stop_all_escs(self) -> None:
        for dev in self._devices:
            if dev._initialized and self._st.serial.is_connected():
                self._st.send_command(f"bdshot {dev._id} stop\n")
            dev._power_slider.set_value_silent(0)

    # ------------------------------------------------------------------
    def _save_config(self) -> None:
        cfg = pool.section("bdshot")
        cfg.num_devices = len(self._devices)
        for i, dev in enumerate(self._devices):
            setattr(cfg, f"device{i + 1}", dev.get_saved_state())
        pool.save()

    def reload_from_config(self) -> None:
        cfg = pool.section("bdshot")
        num = min(cfg.num_devices or len(self._devices), _MAX_DEVICES)
        while len(self._devices) > num:
            self._remove_device()
        while len(self._devices) < num:
            self._add_device()
        for i, dev in enumerate(self._devices):
            saved = getattr(cfg, f"device{i + 1}", {}) or {}
            dev.apply_saved_state({
                "gpio": saved.get("gpio", dev._gpio_combo.currentText()),
                "rate": saved.get("rate", dev._rate_combo.currentText()),
                "bidi": saved.get("bidi", dev._bidi_cb.isChecked()),
                "inverted": saved.get("inverted", dev._dir_cb.isChecked()),
            })

    def closeEvent(self, event) -> None:
        self._save_config()
        super().closeEvent(event)
