"""ESC control window — modernized (DShot-style layout, config on right-click)."""

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from qt_throttled_slider import SliderDispatcher, ThrottledSlider

_FREQUENCY_OPTIONS = ["50Hz", "100Hz", "200Hz", "300Hz"]
_DIRECTION_OPTIONS = ["Normal", "Inverted"]
_MAX_ESCS = 8
_CALIB_LABELS  = ["BW Max", "BW Min", "Idle", "FW Min", "FW Max"]
_CALIB_DEFAULT = [1000, 1500, 1500, 1500, 2000]

# Total time for one ESC's init sequence: 4×200ms cmds + 5×750ms warmup pulses + margin
_INIT_CYCLE_MS = 200 * 4 + 750 * 5 + 300


# ---------------------------------------------------------------------------

class _CalibDialog(QDialog):
    """Calibration-only pane, opened via the Calibrate button on each ESC."""

    def __init__(self, esc_id: int, calib: list, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"ESC {esc_id} — Calibration")
        self.setModal(True)

        layout = QVBoxLayout(self)

        calib_form = QFormLayout()
        calib_form.setHorizontalSpacing(12)
        self._entries: list[QLineEdit] = []
        for lbl, val in zip(_CALIB_LABELS, calib):
            entry = QLineEdit(str(val))
            entry.setFixedWidth(70)
            calib_form.addRow(f"{lbl} (µs):", entry)
            self._entries.append(entry)
        layout.addLayout(calib_form)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def get_calibration(self) -> list:
        try:
            return [int(e.text()) for e in self._entries]
        except ValueError:
            return list(_CALIB_DEFAULT)


# ---------------------------------------------------------------------------

class _ESCWidget(QGroupBox):
    """One ESC row — selected toggle, power slider, Init/Deinit.
    Right-click anywhere on the group box to open the config dialog."""

    def __init__(
        self,
        esc_id: int,
        serial_terminal,
        freq_fn,
        dispatcher: SliderDispatcher,
        state: dict,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(f"ESC {esc_id}", parent)
        self._id = esc_id
        self._st = serial_terminal
        self._freq_fn = freq_fn          # callable → frequency string, e.g. "300Hz"
        self._cfg = dict(state)
        self._initialized = False

        self._build_ui(dispatcher)
        self._update_state()

    # ------------------------------------------------------------------
    def _build_ui(self, dispatcher: SliderDispatcher) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(4)

        # ── Row 1: config ─────────────────────────────────────────────
        cfg_row = QHBoxLayout()
        cfg_row.setSpacing(6)

        self._selected_cb = QCheckBox("Selected")
        self._selected_cb.setChecked(self._cfg.get("selected", True))
        cfg_row.addWidget(self._selected_cb)

        cfg_row.addWidget(QLabel("GPIO:"))
        self._gpio_combo = QtGPIOCombobox()
        self._gpio_combo.set_gpio(self._cfg.get("gpio", str(8 + self._id)))
        self._gpio_combo.setFixedWidth(100)
        cfg_row.addWidget(self._gpio_combo)

        cfg_row.addWidget(QLabel("Dir:"))
        self._dir_combo = QComboBox()
        self._dir_combo.addItems(_DIRECTION_OPTIONS)
        self._dir_combo.setCurrentText(self._cfg.get("direction", "Normal"))
        self._dir_combo.setFixedWidth(90)
        cfg_row.addWidget(self._dir_combo)

        calib_btn = QPushButton("Calibrate…")
        calib_btn.clicked.connect(self._open_calib)
        cfg_row.addWidget(calib_btn)

        cfg_row.addStretch()
        root.addLayout(cfg_row)

        # ── Row 2: power + init/deinit ────────────────────────────────
        ctrl_row = QHBoxLayout()
        ctrl_row.setSpacing(6)

        self._power_slider = ThrottledSlider(
            dispatcher,
            command_fn=lambda v, i=self._id: f"esc {i} pw {v / 100:.2f}",
            label_fn=lambda v: f"{v / 100:.2f}",
            label_width=50,
        )
        self._power_slider.setRange(-100, 100)
        self._power_slider.set_label_style("background: #90EE90; border: 1px inset gray;")
        self._power_slider.valueChanged.connect(self._on_power_changed)
        ctrl_row.addWidget(self._power_slider, stretch=1)

        self._init_btn = QPushButton("Init")
        self._init_btn.clicked.connect(self._do_init)
        self._deinit_btn = QPushButton("Deinit")
        self._deinit_btn.clicked.connect(self._do_deinit)
        ctrl_row.addWidget(self._init_btn)
        ctrl_row.addWidget(self._deinit_btn)

        root.addLayout(ctrl_row)

    def _on_power_changed(self, v: int) -> None:
        if v == 0:
            style = "background: #90EE90; border: 1px inset gray;"
        elif v > 0:
            style = "background: #FFFF00; border: 1px inset gray;"
        else:
            style = "background: #FFA500; border: 1px inset gray;"
        self._power_slider.set_label_style(style)

    # ------------------------------------------------------------------
    def _open_calib(self) -> None:
        dlg = _CalibDialog(self._id, self._cfg.get("calibration", _CALIB_DEFAULT), self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._cfg["calibration"] = dlg.get_calibration()

    # ------------------------------------------------------------------
    def _cmd(self, text: str) -> None:
        if self._st.serial.is_connected():
            self._st.send_command(text + "\n")

    def _do_init(self) -> None:
        gpio    = str(self._gpio_combo.get_gpio() or "")
        dir_num = 0 if self._dir_combo.currentText() == "Normal" else 1
        calib   = self._cfg.get("calibration", _CALIB_DEFAULT)
        freq    = self._freq_fn().replace("Hz", "")

        delay = 0
        QTimer.singleShot(delay, lambda: self._cmd(f"esc freq {freq}"))
        delay += 200
        QTimer.singleShot(delay, lambda: self._cmd(f"esc {self._id} init {gpio}"))
        delay += 200
        QTimer.singleShot(delay, lambda: self._cmd(f"esc {self._id} dir {dir_num}"))
        delay += 200
        cv = " ".join(str(v) for v in calib)
        QTimer.singleShot(delay, lambda: self._cmd(f"esc {self._id} cali {cv}"))
        delay += 200
        for pwr in [0.00, -0.01, 0.00, 0.01, 0.00]:
            QTimer.singleShot(delay, lambda p=pwr: self._cmd(f"esc {self._id} pw {p:.2f}"))
            delay += 750
        QTimer.singleShot(delay, self._mark_initialized)

    def _mark_initialized(self) -> None:
        self._initialized = True
        self._power_slider.set_value_silent(0)
        self._update_state()

    def _do_deinit(self) -> None:
        self._cmd(f"esc {self._id} deinit")
        self._initialized = False
        self._power_slider.set_value_silent(0)
        self._power_slider.set_label_style("background: #90EE90; border: 1px inset gray;")
        self._update_state()

    # ------------------------------------------------------------------
    def on_connection_changed(self) -> None:
        if not self._st.serial.is_connected():
            self._initialized = False
            self._power_slider.set_value_silent(0)
        self._update_state()

    def _update_state(self) -> None:
        connected = self._st.serial.is_connected()
        self._init_btn.setEnabled(connected and not self._initialized)
        self._deinit_btn.setEnabled(connected and self._initialized)
        self._power_slider.setEnabled(self._initialized)
        self._gpio_combo.setEnabled(not self._initialized)
        self._dir_combo.setEnabled(not self._initialized)

    def is_selected(self) -> bool:
        return self._selected_cb.isChecked()

    def get_saved_state(self) -> dict:
        return {
            "gpio": str(self._gpio_combo.get_gpio() or ""),
            "direction": self._dir_combo.currentText(),
            "calibration": self._cfg.get("calibration", _CALIB_DEFAULT),
            "selected": self._selected_cb.isChecked(),
        }

    def apply_saved_state(self, state: dict) -> None:
        self._cfg = dict(state)
        self._gpio_combo.set_gpio(state.get("gpio", str(8 + self._id)))
        self._dir_combo.setCurrentText(state.get("direction", "Normal"))
        self._selected_cb.setChecked(state.get("selected", True))


# ---------------------------------------------------------------------------

class ESCControlWindow(QWidget):
    """ESC control panel — up to 8 ESCs, per-ESC config on right-click."""

    def __init__(self, serial_terminal, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("ESC Control")
        self.setWindowFlag(Qt.WindowType.Window)
        self._st = serial_terminal
        self._escs: list[_ESCWidget] = []
        self._dispatcher = SliderDispatcher(serial_terminal)

        self._build_ui()
        self._load_config()
        serial_terminal.register_connection_state_callback(self._on_connection_changed)
        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ── Common header ─────────────────────────────────────────────
        common = QGroupBox("Common")
        common_row = QHBoxLayout(common)
        common_row.addWidget(QLabel("Frequency:"))
        self._freq_combo = QComboBox()
        self._freq_combo.addItems(_FREQUENCY_OPTIONS)
        self._freq_combo.setCurrentText("300Hz")
        self._freq_combo.setFixedWidth(80)
        common_row.addWidget(self._freq_combo)
        common_row.addStretch()
        self._init_all_btn = QPushButton("Init Selected")
        self._init_all_btn.clicked.connect(self._init_selected)
        self._deinit_all_btn = QPushButton("Deinit Selected")
        self._deinit_all_btn.clicked.connect(self._deinit_selected)
        common_row.addWidget(self._init_all_btn)
        common_row.addWidget(self._deinit_all_btn)
        root.addWidget(common)

        # ── ESC rows ──────────────────────────────────────────────────
        self._esc_layout = QVBoxLayout()
        self._esc_layout.setSpacing(4)
        root.addLayout(self._esc_layout)

        # ── Add / Remove ──────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("+ Add ESC")
        self._add_btn.clicked.connect(lambda: self._add_esc())
        self._remove_btn = QPushButton("− Remove Last")
        self._remove_btn.clicked.connect(self._remove_esc)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._remove_btn)
        btn_row.addStretch()
        root.addLayout(btn_row)

    # ------------------------------------------------------------------
    def _default_state(self, esc_id: int) -> dict:
        return {
            "gpio": str(8 + esc_id),
            "direction": "Normal",
            "calibration": list(_CALIB_DEFAULT),
            "selected": True,
        }

    def _add_esc(self, state: dict | None = None) -> None:
        if len(self._escs) >= _MAX_ESCS:
            return
        esc_id = len(self._escs) + 1
        esc = _ESCWidget(
            esc_id,
            self._st,
            lambda: self._freq_combo.currentText(),
            self._dispatcher,
            state or self._default_state(esc_id),
        )
        esc._selected_cb.toggled.connect(self._on_connection_changed)
        self._escs.append(esc)
        self._esc_layout.addWidget(esc)
        self._update_buttons()
        self.adjustSize()

    def _remove_esc(self) -> None:
        if not self._escs:
            return
        esc = self._escs.pop()
        self._esc_layout.removeWidget(esc)
        esc.deleteLater()
        self._update_buttons()
        self.adjustSize()

    def _update_buttons(self) -> None:
        self._add_btn.setEnabled(len(self._escs) < _MAX_ESCS)
        self._remove_btn.setEnabled(len(self._escs) > 0)

    # ------------------------------------------------------------------
    def _init_selected(self) -> None:
        delay = 0
        for esc in self._escs:
            if esc.is_selected() and not esc._initialized:
                QTimer.singleShot(delay, esc._do_init)
                delay += _INIT_CYCLE_MS

    def _deinit_selected(self) -> None:
        for esc in self._escs:
            if esc.is_selected() and esc._initialized:
                esc._do_deinit()

    def _on_connection_changed(self) -> None:
        connected = self._st.serial.is_connected()
        any_init = False
        for esc in self._escs:
            esc.on_connection_changed()
            any_init = any_init or esc._initialized
        selected = [e for e in self._escs if e.is_selected()]
        has_uninit = any(not e._initialized for e in selected)
        has_init   = any(e._initialized     for e in selected)
        self._init_all_btn.setEnabled(connected and has_uninit)
        self._deinit_all_btn.setEnabled(connected and has_init)
        self._freq_combo.setEnabled(not any_init)

    # ------------------------------------------------------------------
    # Public API — used by control pad
    # ------------------------------------------------------------------

    @property
    def num_escs(self) -> int:
        return len(self._escs)

    def send_all_esc_power(self, power_levels: list[float]) -> None:
        for i, pwr in enumerate(power_levels[: len(self._escs)]):
            esc = self._escs[i]
            ival = int(pwr * 100)
            esc._power_slider.set_value_silent(ival)
            esc._on_power_changed(ival)
            if esc._initialized and self._st.serial.is_connected():
                self._st.send_command(f"esc {esc._id} pw {pwr:.2f}\n")

    def stop_all_escs(self) -> None:
        self.send_all_esc_power([0.0] * len(self._escs))

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------

    def _save_config(self) -> None:
        cfg = pool.section("esc")
        cfg.num_escs  = len(self._escs)
        cfg.frequency = self._freq_combo.currentText()
        for i, esc in enumerate(self._escs):
            setattr(cfg, f"esc{i + 1}", esc.get_saved_state())
        pool.save()

    def _load_config(self) -> None:
        cfg = pool.section("esc")
        freq = getattr(cfg, "frequency", None)
        if freq:
            self._freq_combo.setCurrentText(freq)
        num = int(getattr(cfg, "num_escs", None) or 0)
        for i in range(num):
            saved = getattr(cfg, f"esc{i + 1}", None) or self._default_state(i + 1)
            self._add_esc(saved)

    def closeEvent(self, event) -> None:
        self._save_config()
        super().closeEvent(event)
