"""Response-parser debug pane — live view of command/response traffic."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

_C_CMD_LIVE = "#2196F3"   # blue   — command in flight
_C_OK       = "#4CAF50"   # green  — completed OK
_C_FAIL     = "#F44336"   # red    — completed FAIL
_C_BODY     = "#888888"   # grey   — response body line
_C_DEBUG    = "#FF9800"   # orange — unattributed / debug
_C_EVENT    = "#9C27B0"   # purple — [EVENT]

# UserRole: base display text (without the "×n" suffix)
_ROLE_BASE = Qt.ItemDataRole.UserRole

_MONO_FONT = QFont("Monospace", 10)
_MONO_FONT.setStyleHint(QFont.StyleHint.Monospace)
_MONO_BOLD = QFont(_MONO_FONT)
_MONO_BOLD.setBold(True)


def _make_item(text: str, color: str, bold: bool = False) -> QTreeWidgetItem:
    item = QTreeWidgetItem([text])
    item.setForeground(0, QColor(color))
    item.setFont(0, _MONO_BOLD if bold else _MONO_FONT)
    return item


class ParserDebugWindow(QWidget):
    """
    Floating window showing live traffic through SerialResponseParser.

    Each sent command appears as a collapsible row:
      ▶ → help  …          while waiting for response
      ▶ → help  (OK)       response arrived — click ▶ to see body lines
        → help  (OK)       no body — no expand arrow

    Consecutive identical entries collapse into one row with a ×n badge:
      ▶ → help  (OK)  ×3

    BLUE   — command in flight
    GREEN  — completed OK      GREY   — body lines (children)
    RED    — completed FAIL    ORANGE — debug/unmatched    PURPLE — event
    """

    def __init__(self, parser, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Response Parser Debug")
        self.setWindowFlag(Qt.WindowType.Window)
        self.resize(700, 480)
        self._parser = parser

        # Tracks in-flight command items: (cmd_text, QTreeWidgetItem)
        self._in_flight: list[tuple[str, QTreeWidgetItem]] = []

        # Deduplication state — reset whenever a non-matching entry arrives
        self._last_sig:   tuple | None        = None
        self._last_item:  QTreeWidgetItem | None = None
        self._last_count: int                 = 0

        self._build_ui()
        self._register_hooks()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(4)

        status_row = QHBoxLayout()
        self._status_lbl = QLabel("pending: 0  |  collecting: no")
        self._status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        status_row.addWidget(self._status_lbl)
        status_row.addStretch()
        reset_btn = QPushButton("Reset Parser")
        reset_btn.setToolTip(
            "Abandon all pending commands and re-sync the parser.\n"
            "Use when responses stopped being processed (desync)."
        )
        reset_btn.setStyleSheet("color: #b03030;")
        reset_btn.clicked.connect(self._reset_parser)
        status_row.addWidget(reset_btn)
        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(64)
        clear_btn.clicked.connect(self._clear)
        status_row.addWidget(clear_btn)
        root.addLayout(status_row)

        self._tree = QTreeWidget()
        self._tree.setHeaderHidden(True)
        self._tree.setIndentation(14)
        self._tree.setFont(_MONO_FONT)
        self._tree.setUniformRowHeights(True)
        root.addWidget(self._tree)

    # ------------------------------------------------------------------
    def _register_hooks(self) -> None:
        p = self._parser
        p.register_sent_callback(self._on_sent)
        p.register_response_callback(self._on_response)
        p.register_debug_callback(self._on_debug)
        p.register_event_callback(self._on_event)

    # ------------------------------------------------------------------
    def _reset_parser(self) -> None:
        n = self._parser.pending_count
        self._parser.reset()
        marker = _make_item(f"—— parser reset ({n} pending abandoned) ——", _C_DEBUG, bold=True)
        self._tree.addTopLevelItem(marker)
        self._tree.scrollToItem(marker)
        # Reset dedupe so the marker never merges with traffic rows
        self._last_sig = None
        self._last_item = None
        self._last_count = 0
        self._update_status()

    def _clear(self) -> None:
        self._tree.clear()
        self._in_flight.clear()
        self._last_sig   = None
        self._last_item  = None
        self._last_count = 0
        self._update_status()

    def _update_status(self) -> None:
        collecting = "yes" if self._parser.is_collecting else "no"
        self._status_lbl.setText(
            f"pending: {self._parser.pending_count}  |  collecting: {collecting}"
        )

    # ------------------------------------------------------------------
    # Deduplication

    def _try_dedupe(self, sig: tuple, item: QTreeWidgetItem) -> None:
        """
        Compare *sig* against the last completed entry.
        • Match  → remove *item*, increment ×n on the kept item, scroll to it.
        • No match → record *item* as the new last entry.
        """
        base_text = item.text(0)

        if sig == self._last_sig and self._last_item is not None:
            self._last_count += 1
            kept_base = self._last_item.data(0, _ROLE_BASE) or self._last_item.text(0)
            self._last_item.setText(0, f"{kept_base}  ×{self._last_count}")
            self._tree.scrollToItem(self._last_item)
            # Remove the duplicate entry that was just added
            idx = self._tree.indexOfTopLevelItem(item)
            if idx >= 0:
                self._tree.takeTopLevelItem(idx)
        else:
            # New unique entry — store base text for future count updates
            item.setData(0, _ROLE_BASE, base_text)
            self._last_sig   = sig
            self._last_item  = item
            self._last_count = 1
            self._tree.scrollToItem(item)

    # ------------------------------------------------------------------
    # Hook callbacks — all called on the main thread

    def _on_sent(self, cmd: str) -> None:
        item = _make_item(f"→ {cmd}  …", _C_CMD_LIVE, bold=True)
        self._tree.addTopLevelItem(item)
        self._in_flight.append((cmd, item))
        # Don't scroll here — wait for the response so we scroll to the final state.
        self._update_status()

    def _on_response(self, cmd: str, body: list[str], status: str) -> None:
        # Claim the earliest in-flight item for this command.
        item: QTreeWidgetItem | None = None
        for i, (pcmd, pitem) in enumerate(self._in_flight):
            if pcmd == cmd:
                item = pitem
                del self._in_flight[i]
                break

        color = _C_OK if status == "OK" else _C_FAIL

        if item is None:
            item = _make_item("", color, bold=True)
            self._tree.addTopLevelItem(item)

        item.setText(0, f"→ {cmd}  ({status})")
        item.setForeground(0, QColor(color))
        item.setFont(0, _MONO_BOLD)

        filtered = [l.strip() for l in body if l.strip()]
        for line in filtered:
            child = _make_item(line, _C_BODY)
            item.addChild(child)

        item.setExpanded(False)

        # Deduplicate on (cmd, status) only — body content can vary (e.g. free
        # heap in help output) and is available via expand regardless.
        self._try_dedupe(("cmd", cmd, status), item)
        self._update_status()

    def _on_debug(self, line: str) -> None:
        item = _make_item(f"? {line}", _C_DEBUG)
        self._tree.addTopLevelItem(item)
        self._try_dedupe(("debug", line), item)
        self._update_status()

    def _on_event(self, line: str) -> None:
        if not self._parser.show_events:
            return
        item = _make_item(line, _C_EVENT)
        self._tree.addTopLevelItem(item)
        self._try_dedupe(("event", line), item)
        self._update_status()
