"""MPU6050 plotter window (Qt port of apps/mpu6050Plotter.py)."""

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

EVENT_MPU6050_GYROSCOPE = "0x14"
EVENT_MPU6050_ACCELERATION = "0x15"
EVENT_MPU6050_SIMPLE = "0x18"


class MPU6050PlotterWindow(QWidget):
    def __init__(self, serial_terminal, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("MPU6050 Plotter")
        self.serial_terminal = serial_terminal

        self._cfg = pool.section("mpu6050", defaults={"sda_gpio": "GPIO37", "scl_gpio": "GPIO36"})
        self._graph_cfg = pool.section("imu", defaults={
            "graph_max_samples": 50,
            "graph_time_span_ms": 3000,
            "draw_graph_interval": 0.05,
            "graph_accel_y_limit": 16,
            "graph_gyro_y_limit": 200,
        })
        self._sda = self._cfg.sda_gpio
        self._scl = self._cfg.scl_gpio
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

        serial_terminal.register_event_callback(EVENT_MPU6050_GYROSCOPE, self._on_gyro)
        serial_terminal.register_event_callback(EVENT_MPU6050_ACCELERATION, self._on_accel)
        serial_terminal.register_event_callback(EVENT_MPU6050_SIMPLE, self._on_simple)
        serial_terminal.register_connection_state_callback(self._on_connection_changed)

        self._draw_timer = QTimer(self)
        self._draw_timer.setInterval(draw_interval)
        self._draw_timer.timeout.connect(self._tick)
        self._draw_timer.start()

    # ------------------------------------------------------------------
    def _build_ui(self, max_samples, timespan, accel_limit, gyro_limit) -> None:
        root = QHBoxLayout(self)

        self._accel_plot = QtPlotGraph(
            title="MPU6050 Acceleration (G)",
            max_samples=max_samples or None,
            timespan=timespan or None,
        )
        self._accel_plot.set_ylim(-accel_limit, accel_limit)
        root.addWidget(self._accel_plot)

        self._fig3d = Figure(figsize=(4, 4), dpi=90)
        self._ax3d = self._fig3d.add_subplot(111, projection="3d")
        self._ax3d.view_init(elev=30, azim=0)
        self._canvas3d = FigureCanvasQTAgg(self._fig3d)
        self._canvas3d.setMinimumSize(300, 300)
        root.addWidget(self._canvas3d)

        self._gyro_plot = QtPlotGraph(
            title="MPU6050 Gyroscope (°/s)",
            max_samples=max_samples or None,
            timespan=timespan or None,
        )
        self._gyro_plot.set_ylim(-accel_limit, accel_limit)
        root.addWidget(self._gyro_plot)

        right = QVBoxLayout()

        cfg_box = QGroupBox("MPU6050 Config")
        cfg_layout = QVBoxLayout(cfg_box)
        gpio_opts = [f"GPIO{i}" for i in range(22)] + [f"GPIO{i}" for i in range(26, 49)]

        for attr, label, default in [("_sda_combo", "SDA:", self._sda), ("_scl_combo", "SCL:", self._scl)]:
            row = QHBoxLayout()
            row.addWidget(QLabel(label))
            combo = QComboBox()
            combo.addItems(gpio_opts)
            combo.setCurrentText(default)
            setattr(self, attr, combo)
            row.addWidget(combo)
            cfg_layout.addLayout(row)

        btn_row = QHBoxLayout()
        self._init_btn = QPushButton("Init")
        self._init_btn.clicked.connect(self._mpu6050_init)
        self._deinit_btn = QPushButton("Deinit")
        self._deinit_btn.clicked.connect(self._mpu6050_deinit)
        btn_row.addWidget(self._init_btn)
        btn_row.addWidget(self._deinit_btn)
        cfg_layout.addLayout(btn_row)
        right.addWidget(cfg_box)

        cali_box = QGroupBox("Calibration")
        cali_layout = QVBoxLayout(cali_box)
        self._cali_acc_btn = QPushButton("Calibrate Accel")
        self._cali_acc_btn.clicked.connect(lambda: self._send_cali("acc"))
        self._cali_gyro_btn = QPushButton("Calibrate Gyro")
        self._cali_gyro_btn.clicked.connect(lambda: self._send_cali("gyro"))
        cali_layout.addWidget(self._cali_acc_btn)
        cali_layout.addWidget(self._cali_gyro_btn)
        right.addWidget(cali_box)

        right.addStretch()
        rw = QWidget()
        rw.setLayout(right)
        root.addWidget(rw)

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
        for _, fi, c in sorted([(np.mean(rv[fi][:,2]), fi, c) for fi, c in faces], key=lambda x: x[0]):
            ax.add_collection3d(Poly3DCollection([rv[fi]], alpha=1.0, facecolor=c, edgecolor="black", linewidth=1))
        o = np.array([1.8, -1.8, -1.8])
        for vec, col in [(np.array([0.6,0,0]),"red"),(np.array([0,0.6,0]),"green"),(np.array([0,0,0.6]),"blue")]:
            ax.quiver(*o, *(vec @ R.T), color=col, arrow_length_ratio=0.3, linewidth=2)
        ax.set_xlim([-2.5,2.5]); ax.set_ylim([-2.5,2.5]); ax.set_zlim([-2.5,2.5])
        ax.set_xticks([]); ax.set_yticks([]); ax.set_zticks([])  # type: ignore
        ax.grid(False)
        ax.set_title(f"Y:{self._yaw:.1f}° P:{self._pitch:.1f}° R:{self._roll:.1f}°")
        self._canvas3d.draw()

    # ------------------------------------------------------------------
    def _on_gyro(self, timestamp: str, data: str) -> None:
        try:
            parts = data.split()
            if len(parts) >= 3:
                t = self._parse_ts(timestamp)
                self._gyro_plot.append_dict(t, {"x-axis": float(parts[0]), "y-axis": float(parts[1]), "z-axis": float(parts[2])})
        except Exception as e:
            print(f"[MPU] gyro error: {e}")

    def _on_accel(self, timestamp: str, data: str) -> None:
        try:
            parts = data.split()
            if len(parts) >= 3:
                t = self._parse_ts(timestamp)
                self._accel_plot.append_dict(t, {"x-axis": float(parts[0]), "y-axis": float(parts[1]), "z-axis": float(parts[2])})
        except Exception as e:
            print(f"[MPU] accel error: {e}")

    def _on_simple(self, timestamp: str, data: str) -> None:
        try:
            parts = data.split()
            if len(parts) >= 3:
                self._yaw, self._pitch, self._roll = float(parts[0]), float(parts[1]), float(parts[2])
        except Exception as e:
            print(f"[MPU] simple error: {e}")

    @staticmethod
    def _parse_ts(ts: str) -> int:
        try:
            return int(float(ts.strip().split()[0]))
        except Exception:
            return int(datetime.now().timestamp() * 1000)

    def _on_connection_changed(self) -> None:
        connected = self.serial_terminal.serial.is_connected()
        self._init_btn.setEnabled(connected and not self._initialized)
        self._deinit_btn.setEnabled(connected and self._initialized)
        self._cali_acc_btn.setEnabled(connected and self._initialized)
        self._cali_gyro_btn.setEnabled(connected and self._initialized)

    def _mpu6050_init(self) -> None:
        if not self.serial_terminal.serial.is_connected():
            return
        self._sda = self._sda_combo.currentText()
        self._scl = self._scl_combo.currentText()
        sda = self._sda.replace("GPIO", "")
        scl = self._scl.replace("GPIO", "")
        self.serial_terminal.send_command(f"mpu6050 init {sda} {scl}\n")
        self._initialized = True
        self._on_connection_changed()
        self._save_config()

    def _mpu6050_deinit(self) -> None:
        if not self.serial_terminal.serial.is_connected():
            return
        self.serial_terminal.send_command("mpu6050 deinit\n")
        self._initialized = False
        self._on_connection_changed()

    def _send_cali(self, sensor: str) -> None:
        if self._initialized:
            self.serial_terminal.send_command(f"mpu6050 cali {sensor}")

    def _save_config(self) -> None:
        self._cfg.sda_gpio = self._sda
        self._cfg.scl_gpio = self._scl
        pool.save()

    def closeEvent(self, event) -> None:
        self._draw_timer.stop()
        super().closeEvent(event)
