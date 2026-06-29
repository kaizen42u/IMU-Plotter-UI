"""Control pad window with keyboard bindings (Qt port of apps/controlPadApp.py)."""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config_store import pool

_cfg = pool.section("control_pad")

_BTN_STYLES = {
    "movement": ("background:#ADD8E6;", "background:#1E90FF;"),
    "stop":     ("background:#F08080;", "background:#FF0000;"),
    "rotation": ("background:#FFFFE0;", "background:#FFD700;"),
    "vertical": ("background:#D3D3D3;", "background:#2E8B57;"),
    "light":    ("background:#DCDCDC;", "background:#808080;"),
}


def _styled_btn(text: str, kind: str, w: int = 100, h: int = 70) -> QPushButton:
    btn = QPushButton(text)
    btn.setFixedSize(w, h)
    normal, pressed = _BTN_STYLES[kind]
    btn.setStyleSheet(f"QPushButton {{ {normal} }} QPushButton:pressed {{ {pressed} }}")
    return btn


class ControlPadWindow(QWidget):
    def __init__(
        self,
        serial_terminal,
        light_control_app=None,
        esc_control_app=None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Control Pad")
        self.serial_terminal = serial_terminal
        self.light_control_app = light_control_app
        self.esc_control_app = esc_control_app
        self._custom_power: dict[str, list[float]] = {}

        self._build_ui()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QHBoxLayout(self)

        # --- Movement cluster ---
        move_box = QGroupBox("Movement")
        move_grid = _GridLayout3x3()
        self._fwd_btn = _styled_btn("Forward", "movement")
        self._fwd_btn.clicked.connect(self._esc_forward)
        self._fwd_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._fwd_btn.customContextMenuRequested.connect(lambda: self._show_editor("forward"))
        move_grid.place(0, 1, self._fwd_btn)

        self._left_btn = _styled_btn("Rotate\nLeft", "movement")
        self._left_btn.clicked.connect(self._esc_left)
        self._left_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._left_btn.customContextMenuRequested.connect(lambda: self._show_editor("rotate_left"))
        move_grid.place(1, 0, self._left_btn)

        self._stop1_btn = _styled_btn("Stop", "stop")
        self._stop1_btn.clicked.connect(self._stop_escs)
        move_grid.place(1, 1, self._stop1_btn)

        self._right_btn = _styled_btn("Rotate\nRight", "movement")
        self._right_btn.clicked.connect(self._esc_right)
        self._right_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._right_btn.customContextMenuRequested.connect(lambda: self._show_editor("rotate_right"))
        move_grid.place(1, 2, self._right_btn)

        self._bwd_btn = _styled_btn("Backward", "movement")
        self._bwd_btn.clicked.connect(self._esc_backward)
        self._bwd_btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._bwd_btn.customContextMenuRequested.connect(lambda: self._show_editor("backward"))
        move_grid.place(2, 1, self._bwd_btn)

        move_box.setLayout(move_grid)
        root.addWidget(move_box)

        # --- Rotation cluster ---
        rot_box = QGroupBox("Rotation")
        rot_grid = _GridLayout3x3()

        self._up_btn = _styled_btn("Up", "vertical")
        self._up_btn.clicked.connect(self._esc_up)
        rot_grid.place(0, 1, self._up_btn)

        self._roll_left_btn = _styled_btn("Roll\nLeft", "rotation")
        self._roll_left_btn.clicked.connect(self._esc_roll_left)
        rot_grid.place(1, 0, self._roll_left_btn)

        self._stop2_btn = _styled_btn("Stop", "stop")
        self._stop2_btn.clicked.connect(self._stop_escs)
        rot_grid.place(1, 1, self._stop2_btn)

        self._roll_right_btn = _styled_btn("Roll\nRight", "rotation")
        self._roll_right_btn.clicked.connect(self._esc_roll_right)
        rot_grid.place(1, 2, self._roll_right_btn)

        self._down_btn = _styled_btn("Down", "vertical")
        self._down_btn.clicked.connect(self._esc_down)
        rot_grid.place(2, 1, self._down_btn)

        rot_box.setLayout(rot_grid)
        root.addWidget(rot_box)

        # --- Light cluster ---
        light_box = QGroupBox("Light")
        light_layout = QVBoxLayout(light_box)
        self._light_up_btn = _styled_btn("+Light", "light", w=90, h=60)
        self._light_up_btn.clicked.connect(self._increase_light)
        self._light_dn_btn = _styled_btn("-Light", "light", w=90, h=60)
        self._light_dn_btn.clicked.connect(self._decrease_light)
        light_layout.addWidget(self._light_up_btn)
        light_layout.addWidget(self._light_dn_btn)
        light_layout.addStretch()
        root.addWidget(light_box)

        self.adjustSize()

    # ------------------------------------------------------------------
    # Keyboard control
    # ------------------------------------------------------------------

    _KEY_MAP = {
        Qt.Key.Key_W: "_fwd_btn",
        Qt.Key.Key_S: "_bwd_btn",
        Qt.Key.Key_A: "_left_btn",
        Qt.Key.Key_D: "_right_btn",
        Qt.Key.Key_U: "_up_btn",
        Qt.Key.Key_J: "_down_btn",
        Qt.Key.Key_I: "_roll_left_btn",
        Qt.Key.Key_K: "_roll_right_btn",
        Qt.Key.Key_O: "_light_up_btn",
        Qt.Key.Key_L: "_light_dn_btn",
    }

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat():
            return
        key = event.key()
        if key == Qt.Key.Key_X:
            for b in (self._stop1_btn, self._stop2_btn):
                b.setDown(True)
            self._stop_escs()
            return
        attr = self._KEY_MAP.get(key)
        if attr:
            btn: QPushButton = getattr(self, attr)
            btn.setDown(True)
            btn.click()

    def keyReleaseEvent(self, event: QKeyEvent) -> None:
        if event.isAutoRepeat():
            return
        key = event.key()
        if key == Qt.Key.Key_X:
            for b in (self._stop1_btn, self._stop2_btn):
                b.setDown(False)
            return
        attr = self._KEY_MAP.get(key)
        if attr:
            getattr(self, attr).setDown(False)

    # ------------------------------------------------------------------
    # ESC actions
    # ------------------------------------------------------------------

    def _esc_forward(self) -> None:
        self._send_power("forward", [-0.15, 0.15, 0.0, 0.10])

    def _esc_backward(self) -> None:
        self._send_power("backward", [0.20, -0.20, 0.0, -0.15])

    def _esc_left(self) -> None:
        self._send_power("rotate_left", [0.0, 0.0, -0.15, -0.03])

    def _esc_right(self) -> None:
        self._send_power("rotate_right", [0.0, 0.0, 0.50, -0.03])

    def _esc_up(self) -> None:
        self._send_power("up", [0.25, 0.25, 0.0, 0.0])

    def _esc_down(self) -> None:
        self._send_power("down", [-0.15, -0.15, 0.0, 0.0])

    def _esc_roll_left(self) -> None:
        self._send_power("roll_left", [0.75, -0.3, 0.0, 0.0])

    def _esc_roll_right(self) -> None:
        self._send_power("roll_right", [-0.425, 0.6, 0.0, 0.0])

    def _stop_escs(self) -> None:
        if self.esc_control_app:
            n = self.esc_control_app.num_escs
            levels = self._custom_power.get("stop") or getattr(_cfg, "stop", None) or [0.0] * n
            self.esc_control_app.send_all_esc_power(levels)

    def _send_power(self, action: str, default: list[float]) -> None:
        if self.esc_control_app:
            levels = self._custom_power.get(action) or getattr(_cfg, action, None) or default
            self.esc_control_app.send_all_esc_power(levels)

    def _increase_light(self) -> None:
        if self.light_control_app:
            self.light_control_app.increase_power()

    def _decrease_light(self) -> None:
        if self.light_control_app:
            self.light_control_app.decrease_power()

    # ------------------------------------------------------------------
    # Power level editor
    # ------------------------------------------------------------------

    def _show_editor(self, action: str) -> None:
        if not self.esc_control_app:
            return
        n = self.esc_control_app.num_escs
        current = (self._custom_power.get(action) or getattr(_cfg, action, None) or [0.0]*n)[:n]
        while len(current) < n:
            current.append(0.0)

        dlg = QDialog(self)
        dlg.setWindowTitle(f"Edit {action.replace('_',' ').title()} Power Levels")
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(f"ESC Power Levels (-1.0 to 1.0)"))

        form = QFormLayout()
        spinboxes: list[QDoubleSpinBox] = []
        for i, val in enumerate(current):
            sb = QDoubleSpinBox()
            sb.setRange(-1.0, 1.0)
            sb.setSingleStep(0.05)
            sb.setDecimals(2)
            sb.setValue(val)
            spinboxes.append(sb)
            form.addRow(f"ESC {i+1}:", sb)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._custom_power[action] = [sb.value() for sb in spinboxes]
            self._save_custom_power()

    def _save_custom_power(self) -> None:
        for action, levels in self._custom_power.items():
            setattr(_cfg, action, levels)
        pool.save()

    # ------------------------------------------------------------------
    def set_light_control_app(self, app) -> None:
        self.light_control_app = app

    def set_esc_control_app(self, app) -> None:
        self.esc_control_app = app

    def closeEvent(self, event) -> None:
        self._save_custom_power()
        super().closeEvent(event)


class _GridLayout3x3(QHBoxLayout):
    """3×3 positional button grid backed by nested HBox/VBox layouts."""

    def __init__(self) -> None:
        super().__init__()
        from PySide6.QtWidgets import QGridLayout
        self._grid = QGridLayout()
        self._grid.setSpacing(4)
        self.addLayout(self._grid)

    def place(self, row: int, col: int, widget: QWidget) -> None:
        self._grid.addWidget(widget, row, col)
