"""GPIO peripheral pane — grid view of all ESP32-S3 GPIOs."""

import re

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from config_store import pool
from esp32_hw import ESP32S3, GPIO
from qt_spinbox import HSpinBox

_cfg = pool.section("gpio")

_COLS = 8

_MODES = ["disable", "input", "output", "output_od", "input_output_od", "input_output"]
_MODES_EXT = _MODES + ["iomux", "matrix"]  # display-only; not user-settable

_OUTPUT_MODES = {"output", "output_od", "input_output_od", "input_output"}
_INPUT_MODES  = {"input", "input_output_od", "input_output"}

_MODE_SHORT = {
    "disable": "dis", "input": "in", "output": "out",
    "output_od": "out·od", "input_output_od": "io·od", "input_output": "io",
    "iomux": "iomux", "matrix": "matrix",
}

_CELL_W, _BTN_H, _CELL_H = 72, 46, 94

_PULL_BTN_STYLE = """
    QPushButton {{
        font-size: 8pt;
        padding: 1px;
        border: 1px solid #aaa;
        border-radius: 3px;
        background: {bg};
        color: {fg};
    }}
"""


class _HatchOverlay(QWidget):
    """Diagonal-line hatch drawn over a disabled GPIO cell."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
        self.hide()

    def paintEvent(self, event) -> None:
        p = QPainter(self)
        w, h = self.width(), self.height()
        p.setPen(QPen(QColor(80, 80, 80, 55), 1))
        spacing = 7
        for i in range(-h, w + h, spacing):
            p.drawLine(i, 0, i + h, h)


def _darken(hex_color: str, amount: int = 18) -> str:
    r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
    return f"#{max(0,r-amount):02x}{max(0,g-amount):02x}{max(0,b-amount):02x}"



_RE_KV = re.compile(r"(\w[\w\s]*)=([\w()./]+)")

_HL = {
    # level value colors
    "level_1": "#66bb6a",   # green  – HIGH
    "level_0": "#ef5350",   # red    – LOW
    # key color
    "key":     "#90a4ae",
    # section labels  (iomux / sleep / out / in)
    "label":   "#80cbc4",
    # mode value
    "mode":    "#80d8ff",
    # pull active
    "pull_on": "#ffe082",
    # neutral value
    "val":     "#e0e0e0",
    # header (GPIO N:)
    "hdr":     "#ffffff",
}


def _html_kv(key: str, raw_val: str) -> str:
    k = key.strip()
    v = raw_val.strip()
    if k == "level":
        color = _HL["level_1"] if v == "1" else _HL["level_0"]
        display = "HIGH" if v == "1" else "LOW"
        return (f'<span style="color:{_HL["key"]}">{k}=</span>'
                f'<b><span style="color:{color}">{display}</span></b>')
    if k == "mode":
        return (f'<span style="color:{_HL["key"]}">{k}=</span>'
                f'<span style="color:{_HL["mode"]}">{v}</span>')
    if k in ("pu", "pd"):
        color = _HL["pull_on"] if v == "1" else _HL["key"]
        return (f'<span style="color:{_HL["key"]}">{k}=</span>'
                f'<span style="color:{color}">{v}</span>')
    return (f'<span style="color:{_HL["key"]}">{k}=</span>'
            f'<span style="color:{_HL["val"]}">{v}</span>')


def _highlight_gpio_read(lines: list[str]) -> str:
    """Return HTML for the raw gpio N read response lines."""
    parts = []
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        # Header: "GPIO N: level=1 mode=input pu=0 pd=0"
        m_hdr = re.match(r"^(GPIO\s+\d+):\s*(.*)$", line, re.IGNORECASE)
        if m_hdr:
            hdr, rest = m_hdr.groups()
            kvs = "  ".join(_html_kv(k, v) for k, v in _RE_KV.findall(rest))
            parts.append(f'<span style="color:{_HL["hdr"]};font-weight:bold">{hdr}:</span>  {kvs}')
            continue
        # Indented sub-line: "  label: key=val ..."
        m_sub = re.match(r"^\s+([\w]+):\s*(.*)$", line)
        if m_sub:
            label, rest = m_sub.groups()
            kvs_found = _RE_KV.findall(rest)
            if kvs_found:
                kvs = "  ".join(_html_kv(k, v) for k, v in kvs_found)
                parts.append(f'&nbsp;&nbsp;<span style="color:{_HL["label"]}">{label}:</span>  {kvs}')
            else:
                val = rest.strip() or "—"
                parts.append(f'&nbsp;&nbsp;<span style="color:{_HL["label"]}">{label}:</span>'
                             f'  <span style="color:{_HL["val"]}">{val}</span>')
            continue
        parts.append(f'<span style="color:{_HL["val"]}">{line}</span>')
    return "<br>".join(parts)


class _ReadPopup(QWidget):
    """Frameless popup showing highlighted 'gpio N read' output. Closes on any click outside."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint)
        self.setStyleSheet(
            "QWidget { background: #1e1e1e; border: 1px solid #444; border-radius: 6px; }"
            "QTextBrowser { background: transparent; border: none; font-family: monospace; font-size: 10pt; }"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 8, 10, 8)
        self._browser = QTextBrowser()
        self._browser.setOpenLinks(False)
        self._browser.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._browser.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lay.addWidget(self._browser)

    def show_response(self, lines: list[str], global_pos) -> None:
        html = _highlight_gpio_read(lines)
        self._browser.setHtml(f'<div style="white-space:pre">{html}</div>')
        # size to content
        doc = self._browser.document()
        doc.setTextWidth(doc.idealWidth())
        w = int(doc.idealWidth()) + 24
        h = int(doc.size().height()) + 20
        self._browser.setFixedSize(w, h)
        self.adjustSize()
        self.move(global_pos.x() + 10, global_pos.y() + 10)
        self.show()
        self.raise_()


class _GPIOCell(QWidget):
    """GPIO tile: level button + mode combo + pull-up/down toggles."""

    def __init__(self, gpio: int, window: "GPIOWindow") -> None:
        super().__init__()
        self._gpio       = gpio
        self._win        = window
        self._reserved   = ESP32S3.is_gpio_reserved(GPIO(gpio))
        self._unavailable = ESP32S3.is_gpio_unavailable(GPIO(gpio))
        self._state      = "unknown"
        self._mode:     str | None  = None
        self._pullup:   bool | None = None
        self._pulldown: bool | None = None
        self._out_func:   str | None = None
        self._iomux_func: str | None = None
        self._in_func:    str | None = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)

        # Main level button
        self._btn = QPushButton()
        self._btn.setFixedSize(_CELL_W, _BTN_H)
        self._btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._btn.customContextMenuRequested.connect(self._on_right_click)
        self._btn.clicked.connect(self._on_click)
        self._btn.setToolTip(ESP32S3.get_gpio_warning(GPIO(gpio)) or f"GPIO {gpio}")
        lay.addWidget(self._btn)

        # Mode combo
        self._combo = QComboBox()
        self._combo.setFixedWidth(_CELL_W)
        for full in _MODES_EXT:
            self._combo.addItem(_MODE_SHORT[full], full)
        self._combo.currentIndexChanged.connect(self._on_mode_changed)
        lay.addWidget(self._combo)

        # Pull-up / pull-down toggles
        pull_row = QHBoxLayout()
        pull_row.setContentsMargins(0, 0, 0, 0)
        pull_row.setSpacing(2)

        self._pu_btn = QPushButton("↑ PU")
        self._pu_btn.setCheckable(True)
        self._pu_btn.setFixedHeight(20)
        self._pu_btn.toggled.connect(lambda on: self._on_pull_toggled("pullup", on))
        pull_row.addWidget(self._pu_btn)

        self._pd_btn = QPushButton("↓ PD")
        self._pd_btn.setCheckable(True)
        self._pd_btn.setFixedHeight(20)
        self._pd_btn.toggled.connect(lambda on: self._on_pull_toggled("pulldown", on))
        pull_row.addWidget(self._pd_btn)

        lay.addLayout(pull_row)
        self._hatch = _HatchOverlay(self)
        hatch_h = _CELL_H if self._unavailable else _BTN_H
        self._hatch.setGeometry(0, 0, _CELL_W, hatch_h)

        if self._unavailable:
            self._btn.setEnabled(False)
            self._combo.setEnabled(False)
            self._pu_btn.setEnabled(False)
            self._pd_btn.setEnabled(False)
            self._btn.setToolTip(f"GPIO {gpio} — not present on ESP32-S3")

        self.setFixedSize(_CELL_W, _CELL_H)
        self._repaint()

    # ------------------------------------------------------------------
    def set_level(self, level: int) -> None:
        self._state = "high" if level else "low"
        self._repaint()

    def set_unknown(self) -> None:
        self._state = "unknown"
        self._repaint()

    def set_mode(self, mode: str) -> None:
        self._mode = mode
        idx = self._combo.findData(mode)
        if idx >= 0:
            self._combo.blockSignals(True)
            self._combo.setCurrentIndex(idx)
            self._combo.blockSignals(False)
        self._repaint()

    def update_from_read(self, level: int, mode: str, pullup: bool, pulldown: bool,
                         out_func: str | None = None,
                         iomux_func: str | None = None,
                         in_func: str | None = None) -> None:
        """Apply a full read-back in one shot — single repaint."""
        self._iomux_func = iomux_func if (iomux_func and iomux_func not in ("native", "matrix")) else None
        is_matrix_routed = iomux_func == "matrix" and (
            (out_func and out_func != "GPIO_OUT") or (in_func and in_func != "none")
        )
        display_mode = "iomux" if self._iomux_func else "matrix" if is_matrix_routed else mode
        idx = self._combo.findData(display_mode)
        if idx >= 0:
            self._combo.blockSignals(True)
            self._combo.setCurrentIndex(idx)
            self._combo.blockSignals(False)
        self._mode     = mode
        self._state    = ("high" if level else "low") if mode in _INPUT_MODES else "unknown"
        self._pullup   = pullup
        self._pulldown = pulldown
        if out_func and out_func != "GPIO_OUT" and iomux_func != "matrix":
            self._out_func = re.sub(r"\(sig=\d+\)", "", out_func).strip()
        else:
            self._out_func = None
        if iomux_func == "matrix":
            sig = None
            if in_func and in_func != "none":
                sig = in_func
            elif out_func and out_func != "GPIO_OUT":
                sig = out_func
            self._in_func = re.sub(r"\(sig=\d+\).*", "", sig).strip() if sig else None
        else:
            self._in_func = None
        for btn, active in [(self._pu_btn, pullup), (self._pd_btn, pulldown)]:
            btn.blockSignals(True)
            btn.setChecked(active)
            btn.blockSignals(False)
        self._repaint()

    def set_pull(self, kind: str, enabled: bool) -> None:
        btn = self._pu_btn if kind == "pullup" else self._pd_btn
        btn.blockSignals(True)
        btn.setChecked(enabled)
        btn.blockSignals(False)
        if kind == "pullup":
            self._pullup = enabled
        else:
            self._pulldown = enabled
        self._refresh_pull_style(btn, enabled)

    def reset(self) -> None:
        self._state = "unknown"
        self._mode = self._pullup = self._pulldown = None
        self._combo.blockSignals(True)
        self._combo.setCurrentIndex(0)
        self._combo.blockSignals(False)
        for btn in (self._pu_btn, self._pd_btn):
            btn.blockSignals(True)
            btn.setChecked(False)
            btn.blockSignals(False)
            self._refresh_pull_style(btn, False)
        self._repaint()

    # ------------------------------------------------------------------
    def _repaint(self) -> None:
        label2 = ""
        if self._out_func and self._iomux_func:
            label2 = f"{self._out_func}\n{self._iomux_func}"
            bg, fg = "#fffde7", "#e65100"
        elif self._out_func:
            label2 = self._out_func
            bg, fg = "#fff8e1", "#5d4037"
        elif self._iomux_func:
            label2 = self._iomux_func
            bg, fg = "#fffde7", "#f57f17"
        elif self._in_func:
            label2 = self._in_func
            bg, fg = "#e3f2fd", "#0d47a1"
        elif self._state == "high":
            label2 = "HIGH"
            bg, fg = "#d4edda", "#155724"
        elif self._state == "low":
            label2 = "LOW"
            bg, fg = "#f8d7da", "#721c24"
        else:
            label2 = "?"
            bg, fg = "#e8e8e8", "#333333"
        self._btn.setText(f"GPIO {self._gpio}\n{label2}")

        border_color = "#b8860b" if self._reserved else "#aaaaaa"
        border_width = "2px"    if self._reserved else "1px"

        self._btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {bg};
                color: {fg};
                border: {border_width} solid {border_color};
                border-radius: 4px;
                font-size: 9pt;
                padding: 2px;
                text-align: center;
            }}
            QPushButton:hover {{ background-color: {_darken(bg)}; }}
            QPushButton:pressed {{ background-color: {_darken(bg, 30)}; }}
        """)

        self._refresh_pull_style(self._pu_btn, bool(self._pullup))
        self._refresh_pull_style(self._pd_btn, bool(self._pulldown))

        show_hatch = self._unavailable or self._mode == "disable"
        self._hatch.setVisible(show_hatch)
        if show_hatch:
            self._hatch.raise_()

    def _refresh_pull_style(self, btn: QPushButton, active: bool) -> None:
        if active:
            btn.setStyleSheet(_PULL_BTN_STYLE.format(bg="#ffe082", fg="#5d4037"))
        else:
            btn.setStyleSheet(_PULL_BTN_STYLE.format(bg="#e8e8e8", fg="#555"))

    # ------------------------------------------------------------------
    def _on_right_click(self, pos) -> None:
        global_pos = self._btn.mapToGlobal(pos)
        def on_resp(lines, status):
            self._win._read_popup.show_response(
                [l for l in lines if l.strip()], global_pos
            )
        self._win._send(f"gpio {self._gpio} read", on_resp)

    def _on_click(self) -> None:
        if self._iomux_func or self._in_func:
            self._win._do_get(GPIO(self._gpio))
            return
        if self._mode in _OUTPUT_MODES:
            new_level = 0 if self._state == "high" else 1
            self._win._do_set(GPIO(self._gpio), new_level)
        else:
            self._win._do_get(GPIO(self._gpio))

    def _on_mode_changed(self, index: int) -> None:
        mode = self._combo.itemData(index)
        if mode in ("iomux", "matrix"):
            return
        self._win._do_set_mode(GPIO(self._gpio), mode)

    def _on_pull_toggled(self, kind: str, enabled: bool) -> None:
        self._win._do_set_pull(GPIO(self._gpio), kind, enabled)


# ---------------------------------------------------------------------------

class GPIOWindow(QWidget):
    """GPIO grid — all ESP32-S3 GPIOs at a glance."""

    def __init__(self, serial_terminal, parser=None, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("GPIO")
        self.setWindowFlag(Qt.WindowType.Window)
        self._st     = serial_terminal
        self._parser = parser
        self._cells: dict[int, _GPIOCell] = {}
        self._cols   = int(getattr(_cfg, "cols", None) or _COLS)

        self._read_popup = _ReadPopup(self)

        self._build_ui()
        serial_terminal.register_connection_state_callback(self._on_connection_changed)
        self._on_connection_changed()

    def _send(self, cmd: str, callback=None) -> None:
        if self._parser is not None:
            self._parser.send(cmd, callback)
        elif self._st.serial.is_connected():
            self._st.send_command(cmd + "\n")

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setSpacing(6)

        bar = QHBoxLayout()
        poll_btn = QPushButton("Poll All")
        poll_btn.clicked.connect(self._do_poll_all)
        bar.addWidget(poll_btn)

        bar.addWidget(QLabel("Columns:"))
        self._cols_spin = HSpinBox()
        self._cols_spin.setRange(1, 16)
        self._cols_spin.setValue(self._cols)
        self._cols_spin.valueChanged.connect(self._on_cols_changed)
        bar.addWidget(self._cols_spin)

        bar.addStretch()
        legend = QLabel(
            '<font color="#155724">■</font> HIGH &nbsp;'
            '<font color="#721c24">■</font> LOW &nbsp;'
            '<font color="#888888">■</font> unknown &nbsp;'
            '<font color="#b8860b">⚠</font> reserved'
        )
        legend.setTextFormat(Qt.TextFormat.RichText)
        legend.setStyleSheet("font-size: 10px;")
        bar.addWidget(legend)
        root.addLayout(bar)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        for gpio in ESP32S3.DISPLAY_GPIO_PINS:
            self._cells[int(gpio)] = _GPIOCell(int(gpio), self)

        self._rebuild_grid(self._cols)
        root.addWidget(self._scroll)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet("color: #888; font-size: 11px;")
        root.addWidget(self._status_lbl)

    def _rebuild_grid(self, cols: int) -> None:
        self._cols = cols
        grid_w = QWidget()
        grid = QGridLayout(grid_w)
        grid.setSpacing(4)
        grid.setContentsMargins(4, 4, 4, 4)
        for idx, gpio in enumerate(ESP32S3.DISPLAY_GPIO_PINS):
            grid.addWidget(self._cells[int(gpio)], idx // cols, idx % cols)
        self._scroll.setWidget(grid_w)
        n = len(ESP32S3.DISPLAY_GPIO_PINS)
        rows = (n + cols - 1) // cols
        self.resize(min(cols, n) * (_CELL_W + 4) + 24, rows * (_CELL_H + 4) + 80)

    def _on_cols_changed(self, cols: int) -> None:
        self._rebuild_grid(cols)
        _cfg.cols = cols
        pool.save()

    def _do_get(self, gpio: GPIO) -> None:
        def on_resp(lines, status):
            cell = self._cells[int(gpio)]
            if status != "OK":
                cell.set_unknown()
                return
            main_line = ""
            level = mode = pullup = pulldown = None
            out_func = iomux_func = in_func = None
            for line in lines:
                m = re.search(r"level=(\d+).*mode=(\w+).*pu=(\d+).*pd=(\d+)", line, re.IGNORECASE)
                if m:
                    level, mode, pullup, pulldown = m.groups()
                    main_line = line.strip()
                m_out = re.match(r"\s+out:\s*(\S+)", line)
                if m_out:
                    out_func = m_out.group(1)
                m_iomux = re.match(r"\s+iomux:.*func=\d+\(([^)]+)\)", line)
                if m_iomux:
                    iomux_func = m_iomux.group(1)
                m_in = re.match(r"\s+in:\s*(\S+)", line)
                if m_in:
                    in_func = m_in.group(1)
            if level is not None:
                cell.update_from_read(int(level), mode, bool(int(pullup)), bool(int(pulldown)),
                                      out_func, iomux_func, in_func)
                self._status_lbl.setText(f"GPIO {gpio}: {main_line}")
        self._send(f"gpio {gpio} read", on_resp)

    def _do_set_mode(self, gpio: GPIO, mode: str) -> None:
        def on_resp(lines, status):
            cell = self._cells[int(gpio)]
            if status == "OK":
                cell.set_mode(mode)
                if mode not in _INPUT_MODES:
                    cell.set_unknown()
                self._status_lbl.setText(f"GPIO {gpio} mode → {mode}")
            else:
                self._status_lbl.setText(f"GPIO {gpio} mode change failed")
                self._do_get(gpio)
        self._send(f"gpio {gpio} config {mode}", on_resp)

    def _do_set(self, gpio: GPIO, level: int) -> None:
        def on_resp(lines, status):
            if status == "OK":
                self._status_lbl.setText(f"GPIO {gpio} set {level} — reading back…")
                self._do_get(gpio)
        self._send(f"gpio {gpio} set {level}", on_resp)

    def _do_set_pull(self, gpio: GPIO, kind: str, enabled: bool) -> None:
        def on_resp(lines, status):
            if status == "OK":
                self._status_lbl.setText(f"GPIO {gpio} {kind} → {'on' if enabled else 'off'} — reading back…")
                self._do_get(gpio)
            else:
                self._cells[int(gpio)].set_pull(kind, not enabled)   # revert toggle
                self._status_lbl.setText(f"GPIO {gpio} {kind} change failed")
        self._send(f"gpio {gpio} {kind} {1 if enabled else 0}", on_resp)

    def _do_poll_all(self) -> None:
        self._status_lbl.setText("Polling all GPIOs…")
        for gpio in ESP32S3.AVAILABLE_GPIO_PINS:  # skip unavailable 22-25
            self._do_get(gpio)

    def _on_connection_changed(self) -> None:
        connected = self._st.serial.is_connected()
        for cell in self._cells.values():
            if cell._unavailable:
                continue
            if not connected:
                cell.reset()
            cell.setEnabled(connected)
