"""Real-time pyqtgraph plot widget (replaces tkPlotGraph / matplotlib-in-Tkinter)."""

import threading
from collections import deque
from typing import Optional

import pyqtgraph as pg
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

pg.setConfigOption("antialias", True)

_COLORS = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD", "#F8B500"]


class QtPlotGraph(QWidget):
    """Scrolling real-time plot backed by pyqtgraph (GPU-accelerated via OpenGL).

    With configurable=True a compact toolbar is added:
      Pause / Clear / Auto-Y / ±Y limit / time span / per-series visibility.
    Pass cfg (a config_store section) to persist toolbar settings across runs.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        title: str = "Graph",
        timespan: Optional[float] = None,
        max_samples: Optional[int] = None,
        configurable: bool = False,
        cfg=None,
    ) -> None:
        super().__init__(parent)
        self.title = title
        self.timespan = timespan
        self.max_samples = max_samples
        self._cfg = cfg

        self._lock = threading.Lock()
        self._timestamps: deque[float] = deque()
        self._series: dict[str, deque[float]] = {}
        self._curves: dict[str, pg.PlotDataItem] = {}
        self._series_cbs: dict[str, QCheckBox] = {}
        self._color_idx = 0
        self._do_ylim = False
        self._ylim = (-1.0, 1.0)
        self._paused = False
        self.data_modified = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        if configurable:
            layout.addLayout(self._build_toolbar())

        self._plot = pg.PlotWidget(title=title)
        self._plot.setBackground("w")
        self._plot.addLegend(offset=(10, 10))
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._plot.getAxis("bottom").setLabel("Time (ms)")
        self._plot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._plot)

        self.setMinimumSize(300, 220)

        if configurable and cfg is not None:
            self._load_cfg()

    # ------------------------------------------------------------------
    # Toolbar
    # ------------------------------------------------------------------

    def _build_toolbar(self) -> QHBoxLayout:
        from qt_spinbox import HSpinBox  # local import to avoid cycles

        bar = QHBoxLayout()
        bar.setSpacing(4)

        self._pause_btn = QPushButton("⏸")
        self._pause_btn.setCheckable(True)
        self._pause_btn.setFixedWidth(28)
        self._pause_btn.setToolTip("Pause/resume plotting (data keeps buffering)")
        self._pause_btn.toggled.connect(self._on_pause_toggled)
        bar.addWidget(self._pause_btn)

        clear_btn = QPushButton("Clear")
        clear_btn.setFixedWidth(48)
        clear_btn.clicked.connect(lambda: self.clear())
        bar.addWidget(clear_btn)

        bar.addSpacing(6)

        self._auto_y_cb = QCheckBox("Auto-Y")
        self._auto_y_cb.toggled.connect(self._on_auto_y_toggled)
        bar.addWidget(self._auto_y_cb)

        bar.addWidget(QLabel("±Y:"))
        self._ylim_spin = HSpinBox()
        self._ylim_spin.setRange(1, 100_000)
        self._ylim_spin.setValue(int(max(abs(self._ylim[0]), abs(self._ylim[1]))))
        self._ylim_spin.setFixedWidth(80)
        self._ylim_spin.valueChanged.connect(self._on_ylim_changed)
        bar.addWidget(self._ylim_spin)

        bar.addWidget(QLabel("Span:"))
        self._span_spin = HSpinBox()
        self._span_spin.setRange(500, 600_000)
        self._span_spin.setValue(int(self.timespan) if self.timespan else 3000)
        self._span_spin.setSingleStep(500)
        self._span_spin.setSuffix(" ms")
        self._span_spin.setFixedWidth(110)
        self._span_spin.valueChanged.connect(self._on_span_changed)
        bar.addWidget(self._span_spin)

        bar.addSpacing(6)

        # Per-series visibility checkboxes are appended here as series appear
        self._series_bar = QHBoxLayout()
        self._series_bar.setSpacing(4)
        bar.addLayout(self._series_bar)

        bar.addStretch()
        return bar

    def _on_pause_toggled(self, on: bool) -> None:
        self._paused = on
        self._pause_btn.setText("▶" if on else "⏸")
        if not on:
            self.data_modified = True

    def _on_auto_y_toggled(self, on: bool) -> None:
        if on:
            self._do_ylim = False
            self._plot.enableAutoRange(axis="y")
        else:
            self._do_ylim = True
            v = self._ylim_spin.value()
            self._ylim = (-v, v)
            self._plot.setYRange(-v, v)
        self._ylim_spin.setEnabled(not on)
        self._save_cfg()

    def _on_ylim_changed(self, v: int) -> None:
        self._ylim = (-v, v)
        if self._do_ylim:
            self._plot.setYRange(-v, v)
        self._save_cfg()

    def _on_span_changed(self, ms: int) -> None:
        self.timespan = ms
        self._save_cfg()

    def _on_series_toggled(self, label: str, visible: bool) -> None:
        curve = self._curves.get(label)
        if curve is not None:
            curve.setVisible(visible)

    def _ensure_series_cb(self, label: str, color: str) -> None:
        if label in self._series_cbs or not hasattr(self, "_series_bar"):
            return
        cb = QCheckBox(label)
        cb.setChecked(True)
        cb.setStyleSheet(f"color: {color}; font-weight: bold;")
        cb.toggled.connect(lambda on, l=label: self._on_series_toggled(l, on))
        self._series_cbs[label] = cb
        self._series_bar.addWidget(cb)

    # ------------------------------------------------------------------
    # Config persistence
    # ------------------------------------------------------------------

    def _load_cfg(self) -> None:
        from config_store import pool  # noqa: F401  (pool.save used in _save_cfg)
        auto_y = bool(getattr(self._cfg, "auto_y", False))
        ylim   = int(getattr(self._cfg, "ylim", 0) or 0)
        span   = int(getattr(self._cfg, "span_ms", 0) or 0)
        if ylim:
            self._ylim_spin.setValue(ylim)
            self._ylim = (-ylim, ylim)
        if span:
            self._span_spin.setValue(span)
            self.timespan = span
        self._auto_y_cb.setChecked(auto_y)
        if not auto_y:
            self._do_ylim = True
            self._plot.setYRange(*self._ylim)

    def _save_cfg(self) -> None:
        if self._cfg is None:
            return
        from config_store import pool
        self._cfg.auto_y  = self._auto_y_cb.isChecked()
        self._cfg.ylim    = self._ylim_spin.value()
        self._cfg.span_ms = self._span_spin.value()
        pool.save()

    # ------------------------------------------------------------------
    # Public API matching tkPlotGraph
    # ------------------------------------------------------------------

    def set_ylim(self, low: float, high: float) -> None:
        self._do_ylim = True
        self._ylim = (low, high)
        self._plot.setYRange(low, high)
        if hasattr(self, "_ylim_spin"):
            self._ylim_spin.blockSignals(True)
            self._ylim_spin.setValue(int(max(abs(low), abs(high))))
            self._ylim_spin.blockSignals(False)

    def append_dict(self, timestamp: float, data_dict: dict[str, float]) -> None:
        with self._lock:
            self._timestamps.append(timestamp)
            for label, value in data_dict.items():
                if label not in self._series:
                    self._series[label] = deque()
                self._series[label].append(value)
            self._trim()
        self.data_modified = True

    def append_list(self, timestamp: float, data_list: list[float]) -> None:
        self.append_dict(timestamp, {f"Series {i+1}": v for i, v in enumerate(data_list)})

    def append_single(self, timestamp: float, data: float) -> None:
        self.append_dict(timestamp, {"Series 1": data})

    def draw(self) -> None:
        """Refresh plot curves from current buffer. Call from the main thread."""
        if not self.data_modified or self._paused:
            return
        self.data_modified = False

        with self._lock:
            ts = list(self._timestamps)
            series_snap = {k: list(v) for k, v in self._series.items()}

        for label, values in series_snap.items():
            if label not in self._curves:
                color = _COLORS[self._color_idx % len(_COLORS)]
                self._color_idx += 1
                pen = pg.mkPen(color=color, width=1.5)
                self._curves[label] = self._plot.plot(pen=pen, name=label)
                self._ensure_series_cb(label, color)
            if ts and len(values) == len(ts):
                self._curves[label].setData(ts, values)

        if self.timespan is not None and ts:
            latest = ts[-1]
            self._plot.setXRange(latest - self.timespan, latest, padding=0)
        elif len(ts) >= 2:
            self._plot.setXRange(ts[0], ts[-1], padding=0.02)

        if self._do_ylim:
            self._plot.setYRange(*self._ylim)

    def clear(self) -> None:
        with self._lock:
            self._timestamps.clear()
            self._series.clear()
        for curve in self._curves.values():
            self._plot.removeItem(curve)
        self._curves.clear()
        self._color_idx = 0
        # Remove series checkboxes so they re-appear in insertion order
        for cb in self._series_cbs.values():
            cb.setParent(None)
            cb.deleteLater()
        self._series_cbs.clear()
        self.data_modified = True

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _trim(self) -> None:
        if self.timespan is not None and self._timestamps:
            latest = self._timestamps[-1]
            while len(self._timestamps) > 1 and self._timestamps[1] < latest - self.timespan:
                self._timestamps.popleft()
                for s in self._series.values():
                    if s:
                        s.popleft()
        if self.max_samples is not None:
            while len(self._timestamps) > self.max_samples:
                self._timestamps.popleft()
                for s in self._series.values():
                    if s:
                        s.popleft()
