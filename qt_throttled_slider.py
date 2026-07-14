"""
Reusable throttled slider widget with a single background dispatch thread.

Usage
-----
    dispatcher = SliderDispatcher(serial_terminal, interval_ms=100)

    slider = ThrottledSlider(
        dispatcher,
        command_fmt="ledc channel 1 set %d",   # simple integer format
    )
    # OR for float / complex commands:
    slider = ThrottledSlider(
        dispatcher,
        command_fn=lambda v: f"dshot 1 set {v / 100:.3f}",
        label_fn=lambda v: f"{v / 100:.2f}",
    )
    slider.setRange(-100, 100)
    layout.addWidget(slider, stretch=1)

One SliderDispatcher should be created per window and shared across all its
ThrottledSlider instances.  The background thread wakes every `interval_ms`,
sends the latest pending command per slider (discarding intermediate values),
then sleeps again — so rapid slider drags never spam the serial port.
"""

import itertools
import threading
import time
from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget


# ---------------------------------------------------------------------------

class SliderDispatcher(QObject):
    """
    Background thread that throttles all slider commands for one window.

    The worker thread collects pending commands and emits _send_signal every
    interval_ms.  Because SliderDispatcher is a QObject living on the main
    thread, Qt automatically uses QueuedConnection for the cross-thread signal,
    so _on_send() always executes on the main thread — safe for any Qt call.
    """

    _send_signal = Signal(str)

    def __init__(self, serial_terminal, interval_ms: int = 100) -> None:
        super().__init__()
        self._serial = serial_terminal
        self._interval = interval_ms / 1000.0
        self._pending: dict[int, str] = {}
        self._lock = threading.Lock()
        self._running = True
        # Qt detects the cross-thread gap and uses QueuedConnection automatically.
        self._send_signal.connect(self._on_send)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def submit(self, slider_id: int, cmd: str) -> None:
        """Called from the main thread; stores the latest command for slider_id."""
        with self._lock:
            self._pending[slider_id] = cmd

    def _run(self) -> None:
        while self._running:
            time.sleep(self._interval)
            with self._lock:
                batch = dict(self._pending)
                self._pending.clear()
            for cmd in batch.values():
                self._send_signal.emit(cmd)  # posts to main-thread event queue

    def _on_send(self, cmd: str) -> None:
        """Slot — always called on the main thread via QueuedConnection."""
        if not self._serial.serial.is_connected():
            return
        if not cmd.endswith("\n"):
            cmd += "\n"
        self._serial.send_command(cmd)

    def stop(self) -> None:
        self._running = False


# ---------------------------------------------------------------------------

_id_counter = itertools.count()


class ThrottledSlider(QWidget):
    """
    QSlider + value label that routes every change through a SliderDispatcher.

    Parameters
    ----------
    dispatcher   : SliderDispatcher shared by the owning window.
    command_fmt  : printf-style string with one ``%d`` placeholder,
                   e.g. ``"ledc channel 1 set %d"``.  Ignored when
                   *command_fn* is provided.
    command_fn   : Optional ``(int) -> str`` for complex formatting
                   (floats, multi-part commands, etc.).
    label_fn     : Optional ``(int) -> str`` for label text.
                   Defaults to ``str(value)``.
    label_width  : Fixed pixel width of the value label (default 36).
    orientation  : Slider orientation (default Horizontal).
    """

    value_changed = Signal(int)

    def __init__(
        self,
        dispatcher: SliderDispatcher,
        command_fmt: str = "%d",
        command_fn: Callable[[int], str] | None = None,
        label_fn: Callable[[int], str] | None = None,
        label_width: int = 36,
        orientation: Qt.Orientation = Qt.Orientation.Horizontal,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._dispatcher = dispatcher
        self._command_fmt = command_fmt
        self._command_fn = command_fn
        self._label_fn = label_fn
        self._id = next(_id_counter)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._slider = QSlider(orientation)
        self._slider.valueChanged.connect(self._on_changed)
        layout.addWidget(self._slider, stretch=1)

        self._lbl = QLabel("0")
        self._lbl.setFixedWidth(label_width)
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        layout.addWidget(self._lbl)

    # ------------------------------------------------------------------
    def _on_changed(self, val: int) -> None:
        self._lbl.setText(self._label_fn(val) if self._label_fn else str(val))
        self.value_changed.emit(val)
        cmd = self._command_fn(val) if self._command_fn else self._command_fmt % val
        self._dispatcher.submit(self._id, cmd)

    # ------------------------------------------------------------------
    # QSlider proxy — keeps call-sites identical to plain QSlider usage

    def setRange(self, min_val: int, max_val: int) -> None:
        self._slider.setRange(min_val, max_val)

    def setValue(self, val: int) -> None:
        self._slider.setValue(val)

    def value(self) -> int:
        return self._slider.value()

    def maximum(self) -> int:
        return self._slider.maximum()

    def setEnabled(self, enabled: bool) -> None:
        super().setEnabled(enabled)   # propagates to children; preserves widget size

    def setMinimumWidth(self, w: int) -> None:
        self._slider.setMinimumWidth(w)

    @property
    def valueChanged(self):  # noqa: N802 — mirror QSlider attribute name
        return self._slider.valueChanged

    # ------------------------------------------------------------------
    # Extra helpers

    def set_value_silent(self, val: int) -> None:
        """Update slider position and label without dispatching a command."""
        self._slider.blockSignals(True)
        self._slider.setValue(val)
        self._lbl.setText(self._label_fn(val) if self._label_fn else str(val))
        self._slider.blockSignals(False)

    def set_label_style(self, style: str) -> None:
        """Apply a stylesheet string to the value label (e.g. background colour)."""
        self._lbl.setStyleSheet(style)
