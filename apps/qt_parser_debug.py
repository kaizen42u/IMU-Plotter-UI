"""Response-parser debug pane — live view of command/response traffic."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCursor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# Colour palette (dark-mode friendly, readable on light backgrounds too)
_C_CMD    = "#2196F3"   # blue    — sent command
_C_BODY   = "#555555"   # grey    — response body line
_C_OK     = "#4CAF50"   # green   — OK
_C_FAIL   = "#F44336"   # red     — FAIL
_C_DEBUG  = "#FF9800"   # orange  — unattributed / debug
_C_EVENT  = "#9C27B0"   # purple  — [EVENT]


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


class ParserDebugWindow(QWidget):
    """
    Floating window that shows live traffic through SerialResponseParser.

    Entries:
        BLUE   → command sent via parser.send()
        GREY   → response body line (indented)
        GREEN  → OK status
        RED    → FAIL status
        ORANGE → debug-buffer line (bypassed / unrecognised echo)
        PURPLE → [EVENT] line
    """

    def __init__(self, parser, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Response Parser Debug")
        self.setWindowFlag(Qt.WindowType.Window)
        self.resize(700, 480)
        self._parser = parser
        self._build_ui()
        self._register_hooks()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(4)

        # Status bar
        status_row = QHBoxLayout()
        self._status_lbl = QLabel("pending: 0  |  collecting: no")
        self._status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        status_row.addWidget(self._status_lbl)
        status_row.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(64)
        clear_btn.clicked.connect(self._log.clear if hasattr(self, "_log") else lambda: None)
        status_row.addWidget(clear_btn)
        root.addLayout(status_row)

        # Log area
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)
        font = QFont("Monospace", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._log.setFont(font)
        root.addWidget(self._log)

        # Wire clear button now that _log exists
        clear_btn.clicked.disconnect()
        clear_btn.clicked.connect(self._log.clear)

    # ------------------------------------------------------------------
    def _register_hooks(self) -> None:
        p = self._parser
        p.register_sent_callback(self._on_sent)
        p.register_response_callback(self._on_response)
        p.register_debug_callback(self._on_debug)
        p.register_event_callback(self._on_event)

    # ------------------------------------------------------------------
    def _append(self, html: str) -> None:
        cursor = self._log.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.insertHtml(html + "<br>")
        self._log.setTextCursor(cursor)
        self._log.ensureCursorVisible()
        self._update_status()

    def _update_status(self) -> None:
        collecting = "yes" if self._parser.is_collecting else "no"
        self._status_lbl.setText(
            f"pending: {self._parser.pending_count}  |  collecting: {collecting}"
        )

    # ------------------------------------------------------------------
    # Hook callbacks — all called on the main thread

    def _on_sent(self, cmd: str) -> None:
        self._append(
            f'<span style="color:{_C_CMD};font-weight:bold;">→ {_esc(cmd)}</span>'
        )

    def _on_response(self, cmd: str, body: list[str], status: str) -> None:
        color = _C_OK if status == "OK" else _C_FAIL
        if body:
            for line in body:
                self._append(
                    f'<span style="color:{_C_BODY};">&nbsp;&nbsp;{_esc(line)}</span>'
                )
        self._append(
            f'<span style="color:{color};font-weight:bold;">← {status}'
            f'</span><span style="color:#aaa;font-size:10px;"> ({_esc(cmd)},'
            f' {len(body)} line{"s" if len(body) != 1 else ""})</span>'
        )

    def _on_debug(self, line: str) -> None:
        self._append(
            f'<span style="color:{_C_DEBUG};">? {_esc(line)}</span>'
        )

    def _on_event(self, line: str) -> None:
        if not self._parser.show_events:
            return
        self._append(
            f'<span style="color:{_C_EVENT};">{_esc(line)}</span>'
        )
