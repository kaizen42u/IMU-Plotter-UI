"""Real-time pyqtgraph plot widget (replaces tkPlotGraph / matplotlib-in-Tkinter)."""

import threading
from collections import deque
from typing import Optional

import pyqtgraph as pg
from PySide6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

pg.setConfigOption("antialias", True)

_COLORS = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD", "#F8B500"]


class QtPlotGraph(QWidget):
    """Scrolling real-time plot backed by pyqtgraph (GPU-accelerated via OpenGL)."""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        title: str = "Graph",
        timespan: Optional[float] = None,
        max_samples: Optional[int] = None,
    ) -> None:
        super().__init__(parent)
        self.title = title
        self.timespan = timespan
        self.max_samples = max_samples

        self._lock = threading.Lock()
        self._timestamps: deque[float] = deque()
        self._series: dict[str, deque[float]] = {}
        self._curves: dict[str, pg.PlotDataItem] = {}
        self._color_idx = 0
        self._do_ylim = False
        self._ylim = (-1.0, 1.0)
        self.data_modified = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._plot = pg.PlotWidget(title=title)
        self._plot.setBackground("w")
        self._plot.addLegend(offset=(10, 10))
        self._plot.showGrid(x=True, y=True, alpha=0.3)
        self._plot.getAxis("bottom").setLabel("Time (ms)")
        self._plot.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        layout.addWidget(self._plot)

        self.setMinimumSize(300, 220)

    # ------------------------------------------------------------------
    # Public API matching tkPlotGraph
    # ------------------------------------------------------------------

    def set_ylim(self, low: float, high: float) -> None:
        self._do_ylim = True
        self._ylim = (low, high)
        self._plot.setYRange(low, high)

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
        if not self.data_modified:
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
