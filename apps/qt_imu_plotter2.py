"""Unified IMU plotter — plots BNO085 or MPU6050 data, selectable at runtime."""

from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from config_store import pool
from qt_plot_graph import QtPlotGraph

from apps.qt_attitude3d import Attitude3DWindow

# BNO085 events
EVENT_BNO_ROTATION = "0x10"
EVENT_BNO_ACCEL    = "0x11"
# MPU6050 events
EVENT_MPU_GYRO     = "0x14"
EVENT_MPU_ACCEL    = "0x15"
EVENT_MPU_SIMPLE   = "0x18"

_SRC_BNO = "bno085"
_SRC_MPU = "mpu6050"


class IMUPlotter2Window(QWidget):
    """Source-agnostic IMU plotter: accel graph + orientation graph + 3-D pane."""

    def __init__(self, serial_terminal, parser=None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("IMU Plotter")
        self.setWindowFlag(Qt.WindowType.Window)
        self._st     = serial_terminal
        self._parser = parser

        self._cfg = pool.section("imu_plotter2", defaults={"source": _SRC_BNO})
        self._graph_cfg = pool.section("imu", defaults={
            "graph_max_samples": 50,
            "graph_time_span_ms": 3000,
            "draw_graph_interval": 0.05,
            "graph_accel_y_limit": 16,
            "graph_gyro_y_limit": 200,
        })
        self._source = getattr(self._cfg, "source", None) or _SRC_BNO

        self._yaw = 0.0
        self._pitch = 0.0
        self._roll = 0.0
        self._view3d: Attitude3DWindow | None = None

        self._build_ui()

        # Register all events from both sensors; handlers filter on active source.
        serial_terminal.register_event_callback(EVENT_BNO_ROTATION, self._on_bno_rotation)
        serial_terminal.register_event_callback(EVENT_BNO_ACCEL,    self._on_bno_accel)
        serial_terminal.register_event_callback(EVENT_MPU_GYRO,     self._on_mpu_gyro)
        serial_terminal.register_event_callback(EVENT_MPU_ACCEL,    self._on_mpu_accel)
        serial_terminal.register_event_callback(EVENT_MPU_SIMPLE,   self._on_mpu_simple)

        self._draw_timer = QTimer(self)
        self._draw_timer.setInterval(int(self._graph_cfg.draw_graph_interval * 1000))
        self._draw_timer.timeout.connect(self._tick)
        self._draw_timer.start()

    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        timespan    = self._graph_cfg.graph_time_span_ms or None
        accel_limit = self._graph_cfg.graph_accel_y_limit
        gyro_limit  = self._graph_cfg.graph_gyro_y_limit

        root = QVBoxLayout(self)
        root.setSpacing(6)

        # ── Top bar: source selector + 3D view ────────────────────────
        bar = QHBoxLayout()
        src_box = QGroupBox("Sensor Source")
        src_row = QHBoxLayout(src_box)
        self._bno_radio = QRadioButton("BNO085")
        self._mpu_radio = QRadioButton("MPU6050")
        (self._bno_radio if self._source == _SRC_BNO else self._mpu_radio).setChecked(True)
        self._bno_radio.toggled.connect(self._on_source_changed)
        src_row.addWidget(self._bno_radio)
        src_row.addWidget(self._mpu_radio)
        bar.addWidget(src_box)

        self._view3d_btn = QPushButton("3D View…")
        self._view3d_btn.clicked.connect(self._toggle_3d)
        bar.addWidget(self._view3d_btn)

        bar.addStretch()
        root.addLayout(bar)

        # ── Plots ─────────────────────────────────────────────────────
        plots = QHBoxLayout()

        self._accel_plot = QtPlotGraph(
            title="Acceleration (G)",
            timespan=timespan,
            configurable=True,
            cfg=pool.section("imu2_accel_graph", defaults={
                "auto_y": False, "ylim": accel_limit, "span_ms": timespan or 3000,
            }),
        )
        plots.addWidget(self._accel_plot)

        self._euler_plot = QtPlotGraph(
            title="Euler Angle (Degree)",
            timespan=timespan,
            configurable=True,
            cfg=pool.section("imu2_euler_graph", defaults={
                "auto_y": False, "ylim": gyro_limit, "span_ms": timespan or 3000,
            }),
        )
        plots.addWidget(self._euler_plot)

        root.addLayout(plots)

    # ------------------------------------------------------------------
    def _toggle_3d(self) -> None:
        if self._view3d is None:
            self._view3d = Attitude3DWindow()
        if self._view3d.isVisible():
            self._view3d.close()
        else:
            self._view3d.show()
            self._view3d.raise_()

    def _src_name(self) -> str:
        return "BNO085" if self._source == _SRC_BNO else "MPU6050"

    # ------------------------------------------------------------------
    def _on_source_changed(self) -> None:
        self._source = _SRC_BNO if self._bno_radio.isChecked() else _SRC_MPU
        self._cfg.source = self._source
        pool.save()
        # Reset display state so old sensor's data doesn't linger
        self._yaw = self._pitch = self._roll = 0.0
        self._accel_plot.clear()
        self._euler_plot.clear()

    # ------------------------------------------------------------------
    def _tick(self) -> None:
        if self._accel_plot.data_modified:
            self._accel_plot.draw()
        if self._euler_plot.data_modified:
            self._euler_plot.draw()
        if self._view3d is not None and self._view3d.isVisible():
            self._view3d.set_attitude(self._yaw, self._pitch, self._roll, self._src_name())

    # ------------------------------------------------------------------
    # BNO085 handlers
    def _on_bno_rotation(self, timestamp: str, data: str) -> None:
        if self._source != _SRC_BNO:
            return
        self._apply_euler(timestamp, data)

    def _on_bno_accel(self, timestamp: str, data: str) -> None:
        if self._source != _SRC_BNO:
            return
        self._apply_accel(timestamp, data)

    # MPU6050 handlers
    def _on_mpu_simple(self, timestamp: str, data: str) -> None:
        if self._source != _SRC_MPU:
            return
        self._apply_euler(timestamp, data)

    def _on_mpu_accel(self, timestamp: str, data: str) -> None:
        if self._source != _SRC_MPU:
            return
        self._apply_accel(timestamp, data)

    def _on_mpu_gyro(self, timestamp: str, data: str) -> None:
        # Gyro rates not plotted in unified view; euler comes from 0x18.
        pass

    # Shared appliers
    def _apply_euler(self, timestamp: str, data: str) -> None:
        try:
            parts = data.split()
            if len(parts) >= 3:
                self._yaw, self._pitch, self._roll = (float(parts[0]), float(parts[1]), float(parts[2]))
                t = self._parse_ts(timestamp)
                self._euler_plot.append_dict(t, {
                    "x-axis": self._yaw, "y-axis": self._pitch, "z-axis": self._roll,
                })
        except Exception as e:
            print(f"[IMU2] euler event error: {e}")

    def _apply_accel(self, timestamp: str, data: str) -> None:
        try:
            parts = data.split()
            if len(parts) >= 3:
                t = self._parse_ts(timestamp)
                self._accel_plot.append_dict(t, {
                    "x-axis": float(parts[0]), "y-axis": float(parts[1]), "z-axis": float(parts[2]),
                })
        except Exception as e:
            print(f"[IMU2] accel event error: {e}")

    @staticmethod
    def _parse_ts(ts: str) -> int:
        try:
            return int(float(ts.strip().split()[0]))
        except Exception:
            return int(datetime.now().timestamp() * 1000)

    def closeEvent(self, event) -> None:
        self._draw_timer.stop()
        if self._view3d is not None:
            self._view3d.close()
        super().closeEvent(event)
