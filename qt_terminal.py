"""ANSI-capable terminal widget for Qt (replaces tkTerminal + tkAnsiFormatter)."""

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QTextBlockFormat, QTextCharFormat, QTextCursor,
)
from PySide6.QtWidgets import QPlainTextEdit

# CSI sequences we act on. Two alternatives:
#   1. ESC form  \x1b[<params><final>  — any final byte (real ANSI from firmware),
#      e.g. \x1b[97m (color) or \x1b[2K (erase line).
#   2. bare form [<params>m            — SGR only, params required, used by
#      ansiEncoding.py constants which omit the ESC byte.
# The bare form is restricted to `m` with at least one digit so literals like
# "[EVENT 0x30]" are never mistaken for control sequences.
_CSI_RE = re.compile(r"\x1b\[([0-9;]*)([A-Za-z])|\[([0-9;]+)(m)")

# VSCode Dark+ inspired palette, with fixes:
#   code 30 (black) → dark gray so it's visible on the dark background
#   code 90 (dim)   → medium gray  (was #666666, too close to #1E1E1E)
#   code 97 (bright white) → pure white (was same hex as 37)
_FG: dict[int, str] = {
    30: "#4D4D4D",  31: "#F44747",  32: "#4EC994",  33: "#DCDCAA",
    34: "#569CD6",  35: "#C586C0",  36: "#4FC1FF",  37: "#D4D4D4",
    90: "#858585",  91: "#F97583",  92: "#85E89D",  93: "#FFEA7F",
    94: "#79B8FF",  95: "#B392F0",  96: "#56B6C2",  97: "#FFFFFF",
}
_BG: dict[int, str] = {
    40: "#000000",  41: "#CD3131",  42: "#0DBC79",  43: "#E5E510",
    44: "#2472C8",  45: "#BC3FBC",  46: "#11A8CD",  47: "#E5E5E5",
   100: "#808080", 101: "#F44747", 102: "#4EC994", 103: "#DCDCAA",
   104: "#569CD6", 105: "#C586C0", 106: "#4FC1FF", 107: "#FFFFFF",
}
_DEFAULT_FG = QColor("#D4D4D4")

# Preferred monospace fonts tried in order; last entry is the generic fallback.
_FONT_PREFERENCES = [
    "JetBrains Mono", "Cascadia Code", "Cascadia Mono",
    "Fira Code", "Fira Mono", "Source Code Pro",
    "Ubuntu Mono", "DejaVu Sans Mono", "Liberation Mono",
    "Courier New",
]


def _best_mono_font(size: int) -> QFont:
    available = set(QFontDatabase.families())
    for name in _FONT_PREFERENCES:
        if name in available:
            return QFont(name, size)
    f = QFont()
    f.setFamily("monospace")
    f.setStyleHint(QFont.StyleHint.Monospace)
    f.setPointSize(size)
    return f


def _256color(n: int) -> tuple[int, int, int]:
    if n < 16:
        basic = [
            (0,0,0),(128,0,0),(0,128,0),(128,128,0),(0,0,128),(128,0,128),
            (0,128,128),(192,192,192),(128,128,128),(255,0,0),(0,255,0),
            (255,255,0),(0,0,255),(255,0,255),(0,255,255),(255,255,255),
        ]
        return basic[n]
    if n < 232:
        n -= 16
        b = n % 6; n //= 6
        g = n % 6; n //= 6
        return (n * 51, g * 51, b * 51)
    v = 8 + (n - 232) * 10
    return (v, v, v)


class AnsiTerminal(QPlainTextEdit):
    """Dark-themed read-only terminal with ANSI SGR color support."""

    def __init__(self, parent=None, max_lines: int = 500, autoscroll: bool = True) -> None:
        super().__init__(parent)
        self.max_lines = max_lines
        self.autoscroll = autoscroll

        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setFont(_best_mono_font(11))
        self.setStyleSheet("""
            QPlainTextEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                selection-background-color: #264F78;
                selection-color: #FFFFFF;
            }
            QScrollBar:vertical {
                background: #252526;
                width: 10px;
                margin: 0;
            }
            QScrollBar::handle:vertical {
                background: #4A4A4A;
                min-height: 24px;
                border-radius: 4px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background: #686868;
            }
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal { height: 0; }
        """)
        self.setViewportMargins(4, 2, 4, 2)

        # Block format applied to every inserted paragraph (120 % line height).
        self._block_fmt = QTextBlockFormat()
        self._block_fmt.setLineHeight(120.0, 1)  # 1 = ProportionalHeight

        self._fmt = QTextCharFormat()
        self._reset_fmt()

        # After a carriage return, subsequent text overwrites the current line
        # instead of being inserted; cleared on newline.
        self._overwrite = False

        # rangeChanged fires AFTER Qt recalculates the document layout, so maximum()
        # is always the true current bottom — unlike reading it inside write() which may
        # see the pre-insertion value.
        self.verticalScrollBar().rangeChanged.connect(self._on_scroll_range_changed)

    # ------------------------------------------------------------------

    def _reset_fmt(self) -> None:
        self._fmt = QTextCharFormat()
        self._fmt.setForeground(_DEFAULT_FG)

    def _apply_params(self, params_str: str) -> None:
        params = [int(p) if p else 0 for p in params_str.split(";")]
        i = 0
        while i < len(params):
            p = params[i]
            if p == 0:
                self._reset_fmt()
            elif p == 1:
                self._fmt.setFontWeight(QFont.Weight.Bold)
            elif p == 2:
                self._fmt.setFontWeight(QFont.Weight.Light)
            elif p == 3:
                self._fmt.setFontItalic(True)
            elif p == 4:
                self._fmt.setFontUnderline(True)
            elif p in (21, 22):
                self._fmt.setFontWeight(QFont.Weight.Normal)
            elif p == 23:
                self._fmt.setFontItalic(False)
            elif p == 24:
                self._fmt.setFontUnderline(False)
            elif p in _FG:
                self._fmt.setForeground(QColor(_FG[p]))
            elif p == 39:
                self._fmt.setForeground(_DEFAULT_FG)
            elif p in _BG:
                self._fmt.setBackground(QColor(_BG[p]))
            elif p == 49:
                self._fmt.clearBackground()
            elif p == 38 and i + 1 < len(params):
                sub = params[i + 1]
                if sub == 5 and i + 2 < len(params):
                    r, g, b = _256color(params[i + 2])
                    self._fmt.setForeground(QColor(r, g, b))
                    i += 2
                elif sub == 2 and i + 4 < len(params):
                    self._fmt.setForeground(QColor(params[i+2], params[i+3], params[i+4]))
                    i += 4
                i += 1
            elif p == 48 and i + 1 < len(params):
                sub = params[i + 1]
                if sub == 5 and i + 2 < len(params):
                    r, g, b = _256color(params[i + 2])
                    self._fmt.setBackground(QColor(r, g, b))
                    i += 2
                elif sub == 2 and i + 4 < len(params):
                    self._fmt.setBackground(QColor(params[i+2], params[i+3], params[i+4]))
                    i += 4
                i += 1
            i += 1

    def write(self, text: str) -> None:
        cursor = self.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)

        pos = 0
        for m in _CSI_RE.finditer(text):
            if m.start() > pos:
                self._insert_run(cursor, text[pos : m.start()])
            # Params/final byte come from whichever alternative matched.
            if m.group(2) is not None:      # ESC form: any final byte
                params, final = m.group(1), m.group(2)
            else:                            # bare form: SGR only
                params, final = m.group(3), m.group(4)
            if final == "m":
                self._apply_params(params)
            elif final == "K":
                self._erase_line(cursor, params)
            # Other final bytes are consumed and ignored (cursor moves, etc.).
            pos = m.end()
        if pos < len(text):
            self._insert_run(cursor, text[pos:])

        # Apply line height to every block touched by this insertion.
        cursor.movePosition(QTextCursor.MoveOperation.End)
        cursor.mergeBlockFormat(self._block_fmt)

        # Trim oldest lines to stay within limit.
        doc = self.document()
        while doc.blockCount() > self.max_lines:
            c = QTextCursor(doc.begin())
            c.select(QTextCursor.SelectionType.BlockUnderCursor)
            c.removeSelectedText()
            c.deleteChar()

    def _insert_run(self, cursor: QTextCursor, run: str) -> None:
        """Insert plain text, honoring embedded CR (\\r) and LF (\\n)."""
        segment: list[str] = []
        for ch in run:
            if ch == "\r":
                self._write_segment(cursor, "".join(segment)); segment = []
                cursor.movePosition(QTextCursor.MoveOperation.StartOfBlock)
                self._overwrite = True
            elif ch == "\n":
                self._write_segment(cursor, "".join(segment)); segment = []
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertText("\n", self._fmt)
                self._overwrite = False
            else:
                segment.append(ch)
        self._write_segment(cursor, "".join(segment))

    def _write_segment(self, cursor: QTextCursor, s: str) -> None:
        """Insert a newline-free run; in overwrite mode it replaces chars ahead."""
        if not s:
            return
        if self._overwrite:
            block = cursor.block()
            block_end = block.position() + block.length() - 1
            avail = max(0, block_end - cursor.position())
            n = min(len(s), avail)
            if n > 0:
                cursor.movePosition(
                    QTextCursor.MoveOperation.Right,
                    QTextCursor.MoveMode.KeepAnchor, n,
                )
        cursor.insertText(s, self._fmt)

    def _erase_line(self, cursor: QTextCursor, params: str) -> None:
        """Handle CSI n K — 0: cursor→end, 1: start→cursor, 2: whole line."""
        mode = int(params) if params.strip() else 0
        block = cursor.block()
        start = block.position()
        end = block.position() + block.length() - 1
        cur = cursor.position()
        if mode == 2:
            a, b = start, end
        elif mode == 1:
            a, b = start, cur
        else:
            a, b = cur, end
        cursor.setPosition(a)
        cursor.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
        cursor.removeSelectedText()

    def _on_scroll_range_changed(self, _min: int, max_val: int) -> None:
        if self.autoscroll:
            self.verticalScrollBar().setValue(max_val)

    def set_autoscroll(self, enabled: bool) -> None:
        self.autoscroll = enabled

    def clear_terminal(self) -> None:
        self.clear()
        self._reset_fmt()
