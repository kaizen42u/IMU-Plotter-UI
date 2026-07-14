"""
HSpinBox / HDoubleSpinBox — spin boxes with side-by-side ◀ / value / ▶ buttons.

Drop-in replacements for QSpinBox / QDoubleSpinBox at call-sites that use:
    setRange, setValue, value, setSuffix, setSingleStep, valueChanged
HDoubleSpinBox additionally supports: setDecimals
"""

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QWidget


class _HSpinBase(QWidget):
    """Shared ◀/▶ infrastructure; subclasses handle numeric type specifics."""

    _HOLD_DELAY    = 400   # ms before auto-repeat kicks in
    _HOLD_INTERVAL = 80    # ms between auto-repeat steps

    def __init__(self, parent: QWidget | None = None, width: int = 110) -> None:
        super().__init__(parent)
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
        self._edit.setMinimumHeight(self._dec_btn.sizeHint().height())
        self._edit.installEventFilter(self)
        layout.addWidget(self._edit, stretch=1)

        self._inc_btn = self._make_btn("▶")
        layout.addWidget(self._inc_btn)

        self.setFixedWidth(width)

        self._repeat_timer = QTimer(self)
        self._repeat_timer.setInterval(self._HOLD_INTERVAL)
        self._repeat_delta = 0

        self._dec_btn.pressed.connect(lambda: self._start_repeat(-self._step))
        self._inc_btn.pressed.connect(lambda: self._start_repeat(+self._step))
        self._dec_btn.released.connect(self._stop_repeat)
        self._inc_btn.released.connect(self._stop_repeat)
        self._repeat_timer.timeout.connect(lambda: self._step_by(self._repeat_delta))

    def _make_btn(self, label: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedWidth(24)
        btn.setAutoRepeat(False)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        return btn

    def eventFilter(self, obj, event):
        if obj is self._edit:
            if event.type() == QEvent.Type.FocusIn:
                text = self._edit.text()
                if self._suffix and text.endswith(self._suffix):
                    text = text[: -len(self._suffix)]
                if self._prefix and text.startswith(self._prefix):
                    text = text[len(self._prefix):]
                self._edit.setText(text.strip())
                QTimer.singleShot(0, self._edit.selectAll)
            elif event.type() == QEvent.Type.FocusOut:
                self._on_edit_finished()
        return super().eventFilter(obj, event)

    def setSuffix(self, suffix: str) -> None:
        self._suffix = suffix
        self._update_display()

    def setPrefix(self, prefix: str) -> None:
        self._prefix = prefix
        self._update_display()

    def _start_repeat(self, delta) -> None:
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

    # Subclasses implement these:
    def _update_display(self) -> None: ...
    def _on_edit_finished(self) -> None: ...
    def _step_by(self, delta) -> None: ...


# ---------------------------------------------------------------------------

class HSpinBox(_HSpinBase):
    """Integer spin box — drop-in for QSpinBox."""

    valueChanged = Signal(int)

    def __init__(self, parent: QWidget | None = None, width: int = 110) -> None:
        self._min   = 0
        self._max   = 99
        self._value = 0
        self._step  = 1
        super().__init__(parent, width=width)
        self._edit.setValidator(QIntValidator(self._min, self._max, self))
        self._update_display()

    # -- QSpinBox-compatible API --

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

    def setSingleStep(self, step: int) -> None:
        self._step = max(1, step)

    def setValue(self, value: int) -> None:
        clamped = max(self._min, min(self._max, int(value)))
        if clamped == self._value:
            return
        self._value = clamped
        self._update_display()
        self.valueChanged.emit(self._value)

    def value(self) -> int:
        return self._value

    # -- Internals --

    def _update_display(self) -> None:
        self._edit.setText(f"{self._prefix}{self._value}{self._suffix}")

    def _on_edit_finished(self) -> None:
        text = self._edit.text()
        if self._prefix and text.startswith(self._prefix):
            text = text[len(self._prefix):]
        if self._suffix and text.endswith(self._suffix):
            text = text[: -len(self._suffix)]
        try:
            self.setValue(int(text.strip()))
        except ValueError:
            self._update_display()

    def _step_by(self, delta: int) -> None:
        self.setValue(self._value + delta)


# ---------------------------------------------------------------------------

class HDoubleSpinBox(_HSpinBase):
    """Float spin box — drop-in for QDoubleSpinBox."""

    valueChanged = Signal(float)

    def __init__(self, parent: QWidget | None = None, width: int = 110) -> None:
        self._min      = 0.0
        self._max      = 99.0
        self._value    = 0.0
        self._step     = 1.0
        self._decimals = 2
        super().__init__(parent, width=width)
        self._edit.setValidator(QDoubleValidator(self._min, self._max, self._decimals, self))
        self._update_display()

    # -- QDoubleSpinBox-compatible API --

    def setRange(self, minimum: float, maximum: float) -> None:
        self._min = float(minimum)
        self._max = float(maximum)
        self._edit.setValidator(QDoubleValidator(self._min, self._max, self._decimals, self))
        self._value = max(self._min, min(self._max, self._value))
        self._update_display()

    def setMinimum(self, minimum: float) -> None:
        self.setRange(minimum, self._max)

    def setMaximum(self, maximum: float) -> None:
        self.setRange(self._min, maximum)

    def setSingleStep(self, step: float) -> None:
        self._step = float(step)

    def setDecimals(self, decimals: int) -> None:
        self._decimals = decimals
        self._edit.setValidator(QDoubleValidator(self._min, self._max, self._decimals, self))
        self._update_display()

    def setValue(self, value: float) -> None:
        clamped = max(self._min, min(self._max, float(value)))
        # Round to avoid float noise triggering spurious valueChanged
        clamped = round(clamped, self._decimals)
        if clamped == self._value:
            return
        self._value = clamped
        self._update_display()
        self.valueChanged.emit(self._value)

    def value(self) -> float:
        return self._value

    # -- Internals --

    def _update_display(self) -> None:
        self._edit.setText(f"{self._prefix}{self._value:.{self._decimals}f}{self._suffix}")

    def _on_edit_finished(self) -> None:
        text = self._edit.text()
        if self._prefix and text.startswith(self._prefix):
            text = text[len(self._prefix):]
        if self._suffix and text.endswith(self._suffix):
            text = text[: -len(self._suffix)]
        try:
            self.setValue(float(text.strip()))
        except ValueError:
            self._update_display()

    def _step_by(self, delta: float) -> None:
        self.setValue(self._value + delta)
