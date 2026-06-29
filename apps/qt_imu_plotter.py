"""BNO085 IMU plotter window (Qt port of apps/imuPlotter.py)."""

from datetime import datetime

import matplotlib
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from mpl_toolkits.mplot3d.art3d import Poly3DCollection

matplotlib.use("QtAgg")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from config_store import pool
from qt_plot_graph import QtPlotGraph

EVENT_BNO085_ROTATION_VECTOR = "0x10"
EVENT_BNO085_LINEAR_ACCELERATION = "0x11"


class IMUPlotterWindow(QWidget):
    def __init__(self, serial_terminal, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("IMU Plotter (BNO085)")
        self.serial_terminal = serial_terminal

        self._cfg = pool.section("bno085", defaults={"tx_gpio": "GPIO5", "rx_gpio": "GPIO4"})
        self._graph_cfg = pool.section("imu", defaults={
            "graph_max_samples": 50,
            "graph_time_span_ms": 3000,
            "draw_graph_interval": 0.05,
            "graph_accel_y_limit": 16,
            "graph_gyro_y_limit": 200,
        })
        self._bno085_tx = self._cfg.tx_gpio
        self._bno085_rx = self._cfg.rx_gpio
        self._initialized = False

        max_samples = self._graph_cfg.graph_max_samples
        timespan = self._graph_cfg.graph_time_span_ms
        draw_interval = int(self._graph_cfg.draw_graph_interval * 1000)
        accel_limit = self._graph_cfg.graph_accel_y_limit
        gyro_limit = self._graph_cfg.graph_gyro_y_limit

        self._yaw = 0.0
        self._pitch = 0.0
        self._roll = 0.0

        self._build_ui(max_samples, timespan, accel_limit, gyro_limit)

        serial_terminal.register_event_callback(EVENT_BNO085_ROTATION_VECTOR, self._on_rotation)
        serial_terminal.register_event_callback(EVENT_BNO085_LINEAR_ACCELERATION, self._on_accel)
        serial_terminal.register_connection_state_callback(self._on_connection_changed)

        self._draw_timer = QTimer(self)
        self._draw_timer.setInterval(draw_interval)
        self._draw_timer.timeout.connect(self._tick)
        self._draw_timer.start()

    # ------------------------------------------------------------------
    def _build_ui(self, max_samples, timespan, accel_limit, gyro_limit) -> None:
        root = QHBoxLayout(self)

        # Acceleration graph
        self._accel_plot = QtPlotGraph(
            title="Linear Acceleration (G)",
            max_samples=max_samples or None,
            timespan=timespan or None,
        )
        self._accel_plot.set_ylim(-accel_limit, accel_limit)
        root.addWidget(self._accel_plot)

        # 3-D visualization
        self._fig3d = Figure(figsize=(4, 4), dpi=90)
        self._ax3d = self._fig3d.add_subplot(111, projection="3d")
        self._ax3d.view_init(elev=30, azim=0)
        self._canvas3d = FigureCanvasQTAgg(self._fig3d)
        self._canvas3d.setMinimumSize(300, 300)
        root.addWidget(self._canvas3d)

        # Euler angle graph
        self._gyro_plot = QtPlotGraph(
            title="Euler Angle (Degree)",
            max_samples=max_samples or None,
            timespan=timespan or None,
        )
        self._gyro_plot.set_ylim(-gyro_limit, gyro_limit)
        root.addWidget(self._gyro_plot)

        # Right panel: config + buttons
        right = QVBoxLayout()

        # BNO085 config
        cfg_box = QGroupBox("BNO085 Config")
        cfg_layout = QVBoxLayout(cfg_box)
        gpio_opts = [f"GPIO{i}" for i in range(22)] + [f"GPIO{i}" for i in range(26, 49)]

        tx_row = QHBoxLayout()
        tx_row.addWidget(QLabel("TX:"))
        self._tx_combo = QComboBox()
        self._tx_combo.addItems(gpio_opts)
        self._tx_combo.setCurrentText(self._bno085_tx)
        tx_row.addWidget(self._tx_combo)
        cfg_layout.addLayout(tx_row)

        rx_row = QHBoxLayout()
        rx_row.addWidget(QLabel("RX:"))
        self._rx_combo = QComboBox()
        self._rx_combo.addItems(gpio_opts)
        self._rx_combo.setCurrentText(self._bno085_rx)
        rx_row.addWidget(self._rx_combo)
        cfg_layout.addLayout(rx_row)

        btn_row = QHBoxLayout()
        self._init_btn = QPushButton("Init")
        self._init_btn.clicked.connect(self._bno085_init)
        self._deinit_btn = QPushButton("Deinit")
        self._deinit_btn.clicked.connect(self._bno085_deinit)
        btn_row.addWidget(self._init_btn)
        btn_row.addWidget(self._deinit_btn)
        cfg_layout.addLayout(btn_row)
        right.addWidget(cfg_box)

        # Tare buttons
        tare_box = QGroupBox("Tare")
        tare_layout = QVBoxLayout(tare_box)
        for label, axis in [("Tare XYZ", "xyz"), ("Tare Z", "z"), ("Clear Tare", "clear")]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _, a=axis: self._send_tare(a))
            tare_layout.addWidget(btn)
        right.addWidget(tare_box)

        # Offset buttons
        offset_box = QGroupBox("Offset")
        offset_layout = QVBoxLayout(offset_box)
        for label, mode in [("Null Offsets", "all"), ("Null Offsets (Yaw)", "yaw"), ("Clear Offsets", "clear")]:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _, m=mode: self._send_offset(m))
            offset_layout.addWidget(btn)
        right.addWidget(offset_box)

        right.addStretch()
        right_widget = QWidget()
        right_widget.setLayout(right)
        root.addWidget(right_widget)

        self._on_connection_changed()

    # ------------------------------------------------------------------
    def _tick(self) -> None:
        if self._accel_plot.data_modified:
            self._accel_plot.draw()
        if self._gyro_plot.data_modified:
            self._gyro_plot.draw()
        self._update_3d()

    def _update_3d(self) -> None:
        ax = self._ax3d
        ax.clear()

        verts = np.array([
            [-1.5,-1,-1],[1.5,-1,-1],[1.5,1,-1],[-1.5,1,-1],
            [-1.5,-1, 1],[1.5,-1, 1],[1.5,1, 1],[-1.5,1, 1],
        ])
        yr, pr, rr = (np.radians(a) for a in (self._yaw, self._pitch, self._roll))
        Ry = np.array([[np.cos(yr),-np.sin(yr),0],[np.sin(yr),np.cos(yr),0],[0,0,1]])
        Rp = np.array([[np.cos(pr),0,np.sin(pr)],[0,1,0],[-np.sin(pr),0,np.cos(pr)]])
        Rr = np.array([[1,0,0],[0,np.cos(rr),-np.sin(rr)],[0,np.sin(rr),np.cos(rr)]])
        R = Ry @ Rp @ Rr
        rv = verts @ R.T

        faces = [([0,1,2,3],"cyan"),([4,5,6,7],"blue"),([0,1,5,4],"yellow"),
                 ([2,3,7,6],"green"),([0,3,7,4],"magenta"),([1,2,6,5],"red")]
        depths = [(np.mean(rv[fi][:,2]), fi, c) for fi, c in faces]
        for _, fi, c in sorted(depths, key=lambda x: x[0]):
            ax.add_collection3d(Poly3DCollection([rv[fi]], alpha=1.0, facecolor=c, edgecolor="black", linewidth=1))

        o = np.array([1.8, -1.8, -1.8])
        for vec, col in [(np.array([0.6,0,0]),"red"),(np.array([0,0.6,0]),"green"),(np.array([0,0,0.6]),"blue")]:
            v = vec @ R.T
            ax.quiver(*o, *v, color=col, arrow_length_ratio=0.3, linewidth=2)

        ax.set_xlim([-2.5,2.5]); ax.set_ylim([-2.5,2.5]); ax.set_zlim([-2.5,2.5])
        ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])  # type: ignore
        ax.grid(False)
        ax.set_title(f"Y:{self._yaw:.1f}° P:{self._pitch:.1f}° R:{self._roll:.1f}°")
        self._canvas3d.draw()

    # ------------------------------------------------------------------
    def _on_rotation(self, timestamp: str, data: str) -> None:
        try:
            parts = data.split()
            if len(parts) >= 3:
                self._yaw, self._pitch, self._roll = float(parts[0]), float(parts[1]), float(parts[2])
                t = self._parse_ts(timestamp)
                self._gyro_plot.append_dict(t, {"x-axis": self._yaw, "y-axis": self._pitch, "z-axis": self._roll})
        except Exception as e:
            print(f"[IMU] rotation event error: {e}")

    def _on_accel(self, timestamp: str, data: str) -> None:
        try:
            parts = data.split()
            if len(parts) >= 3:
                t = self._parse_ts(timestamp)
                self._accel_plot.append_dict(t, {"x-axis": float(parts[0]), "y-axis": float(parts[1]), "z-axis": float(parts[2])})
        except Exception as e:
            print(f"[IMU] accel event error: {e}")

    @staticmethod
    def _parse_ts(ts: str) -> int:
        try:
            return int(float(ts.strip().split()[0]))
        except Exception:
            return int(datetime.now().timestamp() * 1000)

    def _on_connection_changed(self) -> None:
        connected = self.serial_terminal.serial.is_connected()
        self._init_btn.setEnabled(connected)
        self._deinit_btn.setEnabled(connected)

    def _bno085_init(self) -> None:
        if not self.serial_terminal.serial.is_connected():
            return
        self._bno085_tx = self._tx_combo.currentText()
        self._bno085_rx = self._rx_combo.currentText()
        tx = self._bno085_tx.replace("GPIO", "")
        rx = self._bno085_rx.replace("GPIO", "")
        self.serial_terminal.send_command(f"bno085 init {tx} {rx}\n")
        self._initialized = True
        self._save_config()

    def _bno085_deinit(self) -> None:
        if not self.serial_terminal.serial.is_connected():
            return
        self.serial_terminal.send_command("bno085 deinit\n")
        self._initialized = False

    def _send_tare(self, axes: str) -> None:
        if self._initialized:
            self.serial_terminal.send_command(f"bno085 tare {axes}")

    def _send_offset(self, mode: str) -> None:
        if self._initialized:
            self.serial_terminal.send_command(f"bno085 offset {mode}")

    def _save_config(self) -> None:
        self._cfg.tx_gpio = self._bno085_tx
        self._cfg.rx_gpio = self._bno085_rx
        pool.save()

    def closeEvent(self, event) -> None:
        self._draw_timer.stop()
        super().closeEvent(event)
