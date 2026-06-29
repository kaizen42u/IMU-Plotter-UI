"""
HSpinBox — integer spin box with side-by-side ◀ / value / ▶ buttons.

Drop-in replacement for QSpinBox at call-sites that use:
    setRange, setValue, value, setSuffix, setSingleStep, valueChanged
"""

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget


class HSpinBox(QWidget):

    valueChanged = Signal(int)

    # How long to hold before auto-repeat starts, and the repeat interval (ms)
    _HOLD_DELAY = 400
    _HOLD_INTERVAL = 80

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._min = 0
        self._max = 99
        self._value = 0
        self._step = 1
        self._suffix = ""
        self._prefix = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(1)

        self._dec_btn = self._make_btn("◀")
        layout.addWidget(self._dec_btn)

        self._edit = QLineEdit()
        self._edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._edit.editingFinished.connect(self._on_edit_finished)
        layout.addWidget(self._edit, stretch=1)

        self._inc_btn = self._make_btn("▶")
        layout.addWidget(self._inc_btn)

        # Auto-repeat timer shared between the two buttons
        self._repeat_timer = QTimer(self)
        self._repeat_timer.setInterval(self._HOLD_INTERVAL)
        self._repeat_delta = 0

        self._dec_btn.pressed.connect(lambda: self._start_repeat(-self._step))
        self._inc_btn.pressed.connect(lambda: self._start_repeat(+self._step))
        self._dec_btn.released.connect(self._stop_repeat)
        self._inc_btn.released.connect(self._stop_repeat)
        self._repeat_timer.timeout.connect(lambda: self._step_by(self._repeat_delta))

        self._update_display()

    # ------------------------------------------------------------------
    def _make_btn(self, label: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedWidth(24)
        btn.setAutoRepeat(False)  # we handle repeat ourselves
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return btn

    # ------------------------------------------------------------------
    # QSpinBox-compatible API

    def setRange(self, minimum: int, maximum: int) -> None:
        self._min = minimum
        self._max = maximum
        self._edit.setValidator(QIntValidator(minimum, maximum, self))
        self._value = max(minimum, min(maximum, self._value))
        self._update_display()

    def setMinimum(self, minimum: int) -> None:
        self.setRange(minimum, self._max)

    def setMaximum(self, maximum: int) -> None:
        self.setRange(self._min, maximum)

    def setValue(self, value: int) -> None:
        clamped = max(self._min, min(self._max, value))
        if clamped == self._value:
            return
        self._value = clamped
        self._update_display()
        self.valueChanged.emit(self._value)

    def value(self) -> int:
        return self._value

    def setSingleStep(self, step: int) -> None:
        self._step = max(1, step)

    def setSuffix(self, suffix: str) -> None:
        self._suffix = suffix
        self._update_display()

    def setPrefix(self, prefix: str) -> None:
        self._prefix = prefix
        self._update_display()

    # ------------------------------------------------------------------
    # Internals

    def _update_display(self) -> None:
        self._edit.setText(f"{self._prefix}{self._value}{self._suffix}")

    def _on_edit_finished(self) -> None:
        text = self._edit.text()
        # Strip prefix/suffix to extract the bare integer
        stripped = text
        if self._prefix and stripped.startswith(self._prefix):
            stripped = stripped[len(self._prefix):]
        if self._suffix and stripped.endswith(self._suffix):
            stripped = stripped[: -len(self._suffix)]
        try:
            self.setValue(int(stripped.strip()))
        except ValueError:
            self._update_display()  # revert to last valid value

    def _step_by(self, delta: int) -> None:
        self.setValue(self._value + delta)

    def _start_repeat(self, delta: int) -> None:
        self._repeat_delta = delta
        self._step_by(delta)
        self._repeat_timer.setInterval(self._HOLD_DELAY)
        self._repeat_timer.setSingleShot(True)
        self._repeat_timer.timeout.connect(self._switch_to_fast)
        self._repeat_timer.start()

    def _switch_to_fast(self) -> None:
        self._repeat_timer.timeout.disconnect(self._switch_to_fast)
        self._repeat_timer.setInterval(self._HOLD_INTERVAL)
        self._repeat_timer.setSingleShot(False)
        self._repeat_timer.timeout.connect(lambda: self._step_by(self._repeat_delta))
        self._repeat_timer.start()

    def _stop_repeat(self) -> None:
        self._repeat_timer.stop()
        try:
            self._repeat_timer.timeout.disconnect()
        except RuntimeError:
            pass

    def wheelEvent(self, event) -> None:
        delta = self._step if event.angleDelta().y() > 0 else -self._step
        self._step_by(delta)
        event.accept()
