"""Terminal configuration window."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (
    QCheckBox,
    QFormLayout,
    QGroupBox,
    QPushButton,
    QSpinBox,
    QComboBox,
    QVBoxLayout,
    QWidget,
)

from config_store import pool
from qt_terminal import _FONT_PREFERENCES


def _available_mono_fonts() -> list[str]:
    available = set(QFontDatabase.families())
    return [f for f in _FONT_PREFERENCES if f in available] or ["Courier New"]


class TerminalConfigWindow(QWidget):
    """Settings panel for the terminal display."""

    def __init__(self, serial_terminal, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Terminal Settings")
        self.setWindowFlag(Qt.WindowType.Window)
        self.setMinimumWidth(300)
        self._st = serial_terminal
        self._build_ui()
        self._load_current()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(8)

        # ── Font ──────────────────────────────────────────────────────
        font_box = QGroupBox("Font")
        font_form = QFormLayout(font_box)
        font_form.setHorizontalSpacing(10)

        self._font_combo = QComboBox()
        self._font_combo.addItems(_available_mono_fonts())
        font_form.addRow("Family:", self._font_combo)

        self._font_size = QSpinBox()
        self._font_size.setRange(6, 32)
        self._font_size.setSuffix(" pt")
        font_form.addRow("Size:", self._font_size)

        root.addWidget(font_box)

        # ── Display ───────────────────────────────────────────────────
        disp_box = QGroupBox("Display")
        disp_form = QFormLayout(disp_box)
        disp_form.setHorizontalSpacing(10)

        self._max_lines = QSpinBox()
        self._max_lines.setRange(100, 10000)
        self._max_lines.setSingleStep(100)
        self._max_lines.setSuffix(" lines")
        disp_form.addRow("Buffer:", self._max_lines)

        self._autoscroll_cb = QCheckBox("Enabled")
        disp_form.addRow("Auto Scroll:", self._autoscroll_cb)

        self._events_cb = QCheckBox("Enabled")
        disp_form.addRow("Show Events:", self._events_cb)

        root.addWidget(disp_box)

        # ── Logging ───────────────────────────────────────────────────
        log_box = QGroupBox("Logging")
        log_form = QFormLayout(log_box)
        log_form.setHorizontalSpacing(10)

        self._logging_cb = QCheckBox("Enabled")
        log_form.addRow("Session log:", self._logging_cb)

        root.addWidget(log_box)

        # ── Apply ─────────────────────────────────────────────────────
        apply_btn = QPushButton("Apply")
        apply_btn.clicked.connect(self._apply)
        root.addWidget(apply_btn)

        root.addStretch()

    # ------------------------------------------------------------------
    def _load_current(self) -> None:
        term = self._st._terminal
        cfg = self._st._cfg

        family = cfg.font_family or term.font().family()
        idx = self._font_combo.findText(family)
        if idx >= 0:
            self._font_combo.setCurrentIndex(idx)

        size = cfg.font_size or term.font().pointSize()
        self._font_size.setValue(size)
        self._max_lines.setValue(term.max_lines)
        self._autoscroll_cb.setChecked(self._st._autoscroll_cb.isChecked())
        self._events_cb.setChecked(self._st._show_events)
        self._logging_cb.setChecked(self._st._logging_checkbox.isChecked())

    def _apply(self) -> None:
        term = self._st._terminal
        cfg = self._st._cfg

        # Font
        font = QFont(self._font_combo.currentText(), self._font_size.value())
        term.setFont(font)
        self._st._cmd_entry.setFont(font)
        cfg.font_family = self._font_combo.currentText()
        cfg.font_size = self._font_size.value()

        # Buffer
        term.max_lines = self._max_lines.value()
        cfg.terminal_max_width = self._max_lines.value()

        # Auto scroll
        self._st._autoscroll_cb.setChecked(self._autoscroll_cb.isChecked())
        cfg.auto_scroll = self._autoscroll_cb.isChecked()

        # Events
        self._st._show_events = self._events_cb.isChecked()
        cfg.show_events = self._events_cb.isChecked()

        # Logging
        self._st._logging_checkbox.setChecked(self._logging_cb.isChecked())
        cfg.logging_enabled = self._logging_cb.isChecked()

        pool.save()
