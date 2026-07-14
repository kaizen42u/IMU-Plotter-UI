"""SDM (Sigma-Delta Modulation) peripheral control pane."""

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
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
from qt_throttled_slider import SliderDispatcher, ThrottledSlider

_NUM_CHANNELS = 8


class _ChannelRow(QWidget):
    def __init__(self, channel_id: int, dispatcher: SliderDispatcher, parent=None) -> None:
        super().__init__(parent)
        self._id          = channel_id
        self._initialized = False

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 1, 0, 1)
        row.setSpacing(4)

        lbl = QLabel(f"Ch {channel_id}:")
        lbl.setFixedWidth(34)
        row.addWidget(lbl)

        row.addWidget(QLabel("GPIO:"))
        self._gpio_combo = QtGPIOCombobox()
        self._gpio_combo.setFixedWidth(88)
        row.addWidget(self._gpio_combo)

        row.addWidget(QLabel("Rate:"))
        self._rate_spin = HSpinBox(width=150)
        self._rate_spin.setRange(312_500, 80_000_000)
        self._rate_spin.setValue(80_000_000)
        self._rate_spin.setSuffix(" Hz")
        row.addWidget(self._rate_spin)

        d_lbl = QLabel("D:")
        d_lbl.setToolTip("Pulse density (0–255)")
        row.addWidget(d_lbl)
        self._density_slider = ThrottledSlider(
            dispatcher,
            command_fmt=f"sdm {channel_id} set %d",  # channel_id is 1-based
            label_width=28,
        )
        self._density_slider.setRange(0, 255)
        self._density_slider.setEnabled(False)
        self._density_slider.setMinimumWidth(80)
        row.addWidget(self._density_slider, stretch=1)

        self._init_btn   = QPushButton("Init")
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

    # ------------------------------------------------------------------
    def set_connected(self, connected: bool) -> None:
        self._init_btn.setEnabled(connected)
        self._set_btn.setEnabled(connected and self._initialized)
        self._deinit_btn.setEnabled(connected and self._initialized)
        self._density_slider.setEnabled(self._initialized)
        self._gpio_combo.setEnabled(not self._initialized)
        self._rate_spin.setEnabled(True)

    def mark_initialized(self, initialized: bool) -> None:
        self._initialized = initialized
        self._init_btn.setText("Reinit" if initialized else "Init")
        if not initialized:
            self._density_slider.set_value_silent(0)
        self._density_slider.setEnabled(initialized)
        self._gpio_combo.setEnabled(not initialized)

    # ------------------------------------------------------------------
    def gpio_num(self)    -> int: return int(self._gpio_combo.get_gpio() or 0)
    def sample_rate(self) -> int: return self._rate_spin.value()
    def density(self)     -> int: return self._density_slider.value()

    def set_gpio(self, gpio) -> None:    self._gpio_combo.set_gpio(str(gpio))
    def set_rate(self, rate: int) -> None: self._rate_spin.setValue(rate)
    def set_density(self, d: int) -> None: self._density_slider.set_value_silent(d)


# ---------------------------------------------------------------------------

class SDMWindow(QWidget):
    """SDM peripheral control pane — 8 channels."""

    def __init__(self, serial_terminal, parser=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("SDM Control")
        self.setWindowFlag(Qt.WindowType.Window)
        self.setMinimumWidth(640)
        self._st         = serial_terminal
        self._parser     = parser
        self._cfg        = pool.section("sdm", defaults={})
        self._dispatcher = SliderDispatcher(serial_terminal)
        self._rows: list[_ChannelRow] = []

        self._build_ui()
        self._load_saved_state()
        serial_terminal.register_connection_state_callback(self._on_connection_changed)
        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        ch_box    = QGroupBox("Channels")
        ch_layout = QVBoxLayout(ch_box)
        ch_layout.setSpacing(2)

        for i in range(1, _NUM_CHANNELS + 1):
            row = _ChannelRow(i, self._dispatcher)
            row._init_btn.clicked.connect(  lambda _, idx=i: self._ch_init(idx))
            row._set_btn.clicked.connect(   lambda _, idx=i: self._ch_set(idx))
            row._deinit_btn.clicked.connect(lambda _, idx=i: self._ch_deinit(idx))
            self._rows.append(row)
            ch_layout.addWidget(row)

        root.addWidget(ch_box)

        bar = QHBoxLayout()
        reload_btn = QPushButton("Reload")
        reload_btn.clicked.connect(self._do_show)
        bar.addWidget(reload_btn)
        bar.addStretch()
        root.addLayout(bar)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self._status_lbl)

        self.adjustSize()

    # ------------------------------------------------------------------
    def _send(self, cmd: str, callback=None) -> None:
        if self._parser is not None:
            self._parser.send(cmd, callback)
        elif self._st.serial.is_connected():
            self._st.send_command(cmd + "\n")

    def _row(self, channel_id: int) -> "_ChannelRow":
        return self._rows[channel_id - 1]

    def _ch_init(self, channel_id: int) -> None:
        row = self._row(channel_id)
        if row._initialized:
            self._send(f"sdm {channel_id} deinit")  # best-effort; ignore result

        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(msg)
            row.mark_initialized(status == "OK")
            self._on_connection_changed()

        self._send(f"sdm {channel_id} init {row.gpio_num()} {row.sample_rate()}", on_resp)

    def _ch_set(self, channel_id: int) -> None:
        row = self._row(channel_id)
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(msg)
        self._send(f"sdm {channel_id} set {row.density()}", on_resp)

    def _ch_deinit(self, channel_id: int) -> None:
        def on_resp(lines, status):
            msg = next((l.strip() for l in lines if l.strip()), status)
            self._status_lbl.setText(msg)
            self._row(channel_id).mark_initialized(False)
            self._on_connection_changed()
        self._send(f"sdm {channel_id} deinit", on_resp)

    def _do_show(self) -> None:
        self._send("sdm show", self._on_show_response)

    def _on_show_response(self, lines: list[str], status: str) -> None:
        if status != "OK":
            return
        for line in lines:
            self._parse_line(line.strip())
        self._on_connection_changed()

    def _parse_line(self, line: str) -> None:
        # "  SDM channel [N] - Free"
        # "  SDM channel [N] - GPIO [14], Rate: 80000000 Hz, Density: 172"
        m = re.match(r"\s*SDM channel \[(\d+)\] - (.+)", line)
        if not m:
            return
        channel_id = int(m.group(1))
        if not (1 <= channel_id <= len(self._rows)):
            return
        body = m.group(2).strip()
        row  = self._row(channel_id)
        if body.lower() == "free":
            row.mark_initialized(False)
            return
        gm = re.search(r"GPIO \[(\d+)\]",      body)
        rm = re.search(r"Rate:\s*(\d+)",        body)
        dm = re.search(r"Density:\s*(\d+)",     body)
        if gm: row.set_gpio(int(gm.group(1)))
        if rm: row.set_rate(int(rm.group(1)))
        if dm: row.set_density(int(dm.group(1)))
        if gm:
            row.mark_initialized(True)

    # ------------------------------------------------------------------
    def _on_connection_changed(self) -> None:
        connected = self._st.serial.is_connected()
        for row in self._rows:
            row.set_connected(connected)

    # ------------------------------------------------------------------
    def _load_saved_state(self) -> None:
        for i, row in enumerate(self._rows, start=1):
            saved = getattr(self._cfg, f"ch{i}", None) or {}
            if saved.get("gpio") is not None:
                row.set_gpio(saved["gpio"])
            if saved.get("rate") is not None:
                row.set_rate(int(saved["rate"]))
            if saved.get("density") is not None:
                row.set_density(int(saved["density"]))

    def _save_config(self) -> None:
        for i, row in enumerate(self._rows, start=1):
            setattr(self._cfg, f"ch{i}", {
                "gpio":    row._gpio_combo.get_gpio(),
                "rate":    row.sample_rate(),
                "density": row.density(),
            })
        pool.save()

    def reload_from_config(self) -> None:
        self._load_saved_state()

    def closeEvent(self, event) -> None:
        self._save_config()
        super().closeEvent(event)
