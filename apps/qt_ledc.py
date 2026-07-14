"""LEDC (LED Control) peripheral monitor pane."""

import re

from config_store import pool

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from qt_gpio_combobox import QtGPIOCombobox
from qt_spinbox import HSpinBox
from qt_throttled_slider import SliderDispatcher, ThrottledSlider

_NUM_TIMERS = 4
_NUM_CHANNELS = 8
_TIMER_IDS = [str(i) for i in range(1, _NUM_TIMERS + 1)]


class _TimerRow(QWidget):
    def __init__(self, timer_id: int, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._id = timer_id
        self._configured = False

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        lbl = QLabel(f"Timer {timer_id + 1}:")
        lbl.setFixedWidth(55)
        row.addWidget(lbl)

        self._hz_spin = HSpinBox()
        self._hz_spin.setRange(1, 80_000_000)
        self._hz_spin.setValue(5000)
        self._hz_spin.setSuffix(" Hz")
        self._hz_spin.setFixedWidth(120)
        row.addWidget(self._hz_spin)

        self._config_btn = QPushButton("Config")
        self._config_btn.setFixedWidth(58)
        self._config_btn.setEnabled(False)
        row.addWidget(self._config_btn)

        self._delete_btn = QPushButton("Delete")
        self._delete_btn.setFixedWidth(58)
        self._delete_btn.setEnabled(False)
        row.addWidget(self._delete_btn)

        row.addStretch()

    def set_connected(self, connected: bool) -> None:
        self._config_btn.setEnabled(connected)
        self._delete_btn.setEnabled(connected and self._configured)

    def mark_configured(self, configured: bool) -> None:
        self._configured = configured
        self._delete_btn.setEnabled(self._config_btn.isEnabled() and configured)

    def hz(self) -> int:
        return self._hz_spin.value()

    def set_hz(self, hz: int) -> None:
        self._hz_spin.setValue(hz)


class _ChannelRow(QWidget):
    def __init__(
        self,
        channel_id: int,
        dispatcher: SliderDispatcher,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._id = channel_id
        self._initialized = False

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 1, 0, 1)
        row.setSpacing(4)

        lbl = QLabel(f"Ch {channel_id + 1}:")
        lbl.setFixedWidth(34)
        row.addWidget(lbl)

        t_lbl = QLabel("T:")
        t_lbl.setToolTip("Timer ID")
        row.addWidget(t_lbl)
        self._timer_combo = QComboBox()
        self._timer_combo.addItems(_TIMER_IDS)
        self._timer_combo.setFixedWidth(46)
        row.addWidget(self._timer_combo)

        g_lbl = QLabel("GPIO:")
        row.addWidget(g_lbl)
        self._gpio_combo = QtGPIOCombobox()
        self._gpio_combo.setFixedWidth(88)
        row.addWidget(self._gpio_combo)

        d_lbl = QLabel("D:")
        d_lbl.setToolTip("Duty (0–256)")
        row.addWidget(d_lbl)
        self._duty_slider = ThrottledSlider(
            dispatcher,
            command_fmt=f"ledc channel {channel_id + 1} set %d",
            label_width=28,
        )
        self._duty_slider.setRange(0, 256)
        self._duty_slider.setEnabled(False)
        self._duty_slider.setMinimumWidth(80)
        row.addWidget(self._duty_slider, stretch=1)

        self._init_btn = QPushButton("Init")
        self._init_btn.setFixedWidth(46)
        self._init_btn.setEnabled(False)
        row.addWidget(self._init_btn)

        self._set_btn = QPushButton("Set")
        self._set_btn.setFixedWidth(38)
        self._set_btn.setEnabled(False)
        row.addWidget(self._set_btn)

        self._deinit_btn = QPushButton("Deinit")
        self._deinit_btn.setFixedWidth(52)
        self._deinit_btn.setEnabled(False)
        row.addWidget(self._deinit_btn)

    def set_connected(self, connected: bool) -> None:
        self._init_btn.setEnabled(connected and not self._initialized)
        self._set_btn.setEnabled(connected and self._initialized)
        self._deinit_btn.setEnabled(connected and self._initialized)
        self._duty_slider.setEnabled(self._initialized)
        self._timer_combo.setEnabled(not self._initialized)
        self._gpio_combo.setEnabled(not self._initialized)

    def mark_initialized(self, initialized: bool) -> None:
        self._initialized = initialized
        if not initialized:
            self._duty_slider.set_value_silent(0)
        self._duty_slider.setEnabled(initialized)
        self._timer_combo.setEnabled(not initialized)
        self._gpio_combo.setEnabled(not initialized)

    def timer_id(self) -> int:
        return int(self._timer_combo.currentText())

    def gpio_num(self) -> int:
        return int(self._gpio_combo.get_gpio() or "0")

    def duty(self) -> int:
        return self._duty_slider.value()

    def set_timer(self, tid: int) -> None:
        self._timer_combo.setCurrentText(str(tid))

    def set_gpio(self, gpio: str) -> None:
        self._gpio_combo.set_gpio(gpio)

    def set_duty(self, duty: int) -> None:
        self._duty_slider.set_value_silent(duty)


class LEDCWindow(QWidget):
    """LEDC peripheral control pane — 4 timers, 8 channels."""

    def __init__(self, serial_terminal, parser=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("LEDC Control")
        self.setWindowFlag(Qt.WindowType.Window)
        self.setMinimumWidth(620)
        self._st = serial_terminal
        self._parser = parser

        self._cfg = pool.section("ledc", defaults={})
        self._dispatcher = SliderDispatcher(serial_terminal)
        self._timer_rows: list[_TimerRow] = []
        self._channel_rows: list[_ChannelRow] = []

        self._build_ui()
        self._load_saved_state()
        serial_terminal.register_connection_state_callback(self._on_connection_changed)
        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        timer_box = QGroupBox("Timers")
        timer_layout = QVBoxLayout(timer_box)
        timer_layout.setSpacing(4)

        for i in range(_NUM_TIMERS):
            row = _TimerRow(i)
            row._config_btn.clicked.connect(lambda checked=False, idx=i: self._timer_config(idx))
            row._delete_btn.clicked.connect(lambda checked=False, idx=i: self._timer_delete(idx))
            self._timer_rows.append(row)
            timer_layout.addWidget(row)

        root.addWidget(timer_box)

        ch_box = QGroupBox("Channels")
        ch_outer = QVBoxLayout(ch_box)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        ch_inner = QWidget()
        ch_layout = QVBoxLayout(ch_inner)
        ch_layout.setSpacing(2)
        ch_layout.setContentsMargins(0, 0, 0, 0)

        for i in range(_NUM_CHANNELS):
            row = _ChannelRow(i, self._dispatcher)
            row._init_btn.clicked.connect(lambda checked=False, idx=i: self._channel_init(idx))
            row._set_btn.clicked.connect(lambda checked=False, idx=i: self._channel_set(idx))
            row._deinit_btn.clicked.connect(lambda checked=False, idx=i: self._channel_deinit(idx))
            self._channel_rows.append(row)
            ch_layout.addWidget(row)

        ch_layout.addStretch()
        scroll.setWidget(ch_inner)
        ch_outer.addWidget(scroll)
        root.addWidget(ch_box)

        bar = QHBoxLayout()
        show_btn = QPushButton("Reload")
        show_btn.clicked.connect(self._do_show)
        bar.addWidget(show_btn)
        bar.addStretch()
        root.addLayout(bar)

    # ------------------------------------------------------------------
    def _cmd(self, *args) -> None:
        if self._st.serial.is_connected():
            self._st.send_command(" ".join(str(a) for a in args) + "\n")

    def _timer_config(self, idx: int) -> None:
        self._cmd("ledc", "timer", idx + 1, "config", self._timer_rows[idx].hz())
        self._timer_rows[idx].mark_configured(True)

    def _timer_delete(self, idx: int) -> None:
        self._cmd("ledc", "timer", idx + 1, "delete")
        self._timer_rows[idx].mark_configured(False)

    def _channel_init(self, idx: int) -> None:
        row = self._channel_rows[idx]
        self._cmd("ledc", "channel", idx + 1, "init", row.timer_id(), row.gpio_num(), row.duty())
        row.mark_initialized(True)
        self._on_connection_changed()

    def _channel_set(self, idx: int) -> None:
        row = self._channel_rows[idx]
        self._cmd("ledc", "channel", idx + 1, "set", row.duty())

    def _channel_deinit(self, idx: int) -> None:
        row = self._channel_rows[idx]
        self._cmd("ledc", "channel", idx + 1, "deinit")
        row.mark_initialized(False)
        self._on_connection_changed()

    def _do_show(self) -> None:
        if self._parser is not None:
            self._parser.send("ledc show", self._on_show_response)
        else:
            self._cmd("ledc", "show")

    def _on_show_response(self, lines: list[str], status: str) -> None:
        if status != "OK":
            return
        section = None
        for line in lines:
            s = line.strip()
            if "=== LEDC Timers ===" in s:
                section = "timers"
            elif "=== LEDC Channels ===" in s:
                section = "channels"
            elif section == "timers":
                self._parse_timer_line(s)
            elif section == "channels":
                self._parse_channel_line(s)
        self._on_connection_changed()

    def _parse_timer_line(self, line: str) -> None:
        # "Timer 1: 500 Hz"  or  "Timer 2: -"
        m = re.match(r"Timer (\d+): (.+)", line)
        if not m:
            return
        idx = int(m.group(1)) - 1
        if not (0 <= idx < len(self._timer_rows)):
            return
        value = m.group(2).strip()
        if value == "-":
            self._timer_rows[idx].mark_configured(False)
        else:
            hz_m = re.match(r"(\d+) Hz", value)
            if hz_m:
                self._timer_rows[idx].set_hz(int(hz_m.group(1)))
                self._timer_rows[idx].mark_configured(True)

    def _parse_channel_line(self, line: str) -> None:
        # "Channel 1: Timer 1 GPIO 0 Duty 146"  or  "Channel 2: -"
        m = re.match(r"Channel (\d+): (.+)", line)
        if not m:
            return
        idx = int(m.group(1)) - 1
        if not (0 <= idx < len(self._channel_rows)):
            return
        value = m.group(2).strip()
        row = self._channel_rows[idx]
        if value == "-":
            row.mark_initialized(False)
        else:
            dm = re.match(r"Timer (\d+) GPIO (\d+) Duty (\d+)", value)
            if dm:
                row.set_timer(int(dm.group(1)))
                row.set_gpio(int(dm.group(2)))
                row.set_duty(int(dm.group(3)))
                row.mark_initialized(True)

    # ------------------------------------------------------------------
    def _on_connection_changed(self) -> None:
        connected = self._st.serial.is_connected()
        for row in self._timer_rows:
            row.set_connected(connected)
        for row in self._channel_rows:
            row.set_connected(connected)

    # ------------------------------------------------------------------
    def _load_saved_state(self) -> None:
        for i, row in enumerate(self._timer_rows):
            saved = getattr(self._cfg, f"timer{i}", None) or {}
            if saved.get("hz"):
                row.set_hz(int(saved["hz"]))
        for i, row in enumerate(self._channel_rows):
            saved = getattr(self._cfg, f"channel{i}", None) or {}
            if saved.get("gpio"):
                row.set_gpio(str(saved["gpio"]))
            if saved.get("timer") is not None:
                row.set_timer(int(saved["timer"]))
            if saved.get("duty") is not None:
                row.set_duty(int(saved["duty"]))

    def _save_config(self) -> None:
        for i, row in enumerate(self._timer_rows):
            setattr(self._cfg, f"timer{i}", {"hz": row.hz()})
        for i, row in enumerate(self._channel_rows):
            setattr(self._cfg, f"channel{i}", {
                "timer": row.timer_id(),
                "gpio": row._gpio_combo.get_gpio(),
                "duty": row.duty(),
            })
        pool.save()

    def reload_from_config(self) -> None:
        self._load_saved_state()

    def closeEvent(self, event) -> None:
        self._save_config()
        super().closeEvent(event)
