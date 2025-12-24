"""IMU Plotter module for displaying accelerometer and gyroscope data."""

import re
import threading
import tkinter as tk
from datetime import datetime

import matplotlib

from tkPlotGraph import tkPlotGraph
from apps.serialTerminal import SerialTerminal
from configManager import get_config_manager

matplotlib.use("Agg")

# Load settings from config
config = get_config_manager()
GRAPH_MAX_SAMPLES = config.get("imu.graph_max_samples", 50)
GRAPH_ACCEL_Y_LIMIT = config.get("imu.graph_accel_y_limit", 16)
GRAPH_GYRO_Y_LIMIT = config.get("imu.graph_gyro_y_limit", 200)
THREAD_PLOTTER_DRAW_GRAPH_INTERVAL = config.get("imu.draw_graph_interval", 0.05)
SERIAL_IMU_BNO085_DATA_REGEX = r"(?:I\s*\(\s*(\d+)\s*\)\s*\w+:\s*)?L\.Accel\s*\(m/s\)\s*-\s*x:\s*([-+]?\d+(?:\.\d+)?)\s*y:\s*([-+]?\d+(?:\.\d+)?)\s*z:\s*([-+]?\d+(?:\.\d+)?)\s*\|\s*Euler\s*\(deg\)\s*-\s*yaw:\s*([-+]?\d+(?:\.\d+)?)\s*pitch:\s*([-+]?\d+(?:\.\d+)?)\s*roll:\s*([-+]?\d+(?:\.\d+)?)"


class IMUPlotter:
    """Handles IMU data plotting (accelerometer and gyroscope graphs)."""

    def __init__(self, master: tk.Tk | tk.Frame, serial_terminal: SerialTerminal) -> None:
        self.master: tk.Tk | tk.Frame = master
        self.serial_terminal: SerialTerminal = serial_terminal
        self.killed: bool = False
        self.stop_event = threading.Event()
        self.show_imu_data: bool = True
        
        self.setup_ui()
        
        # Register callback with SerialTerminal instead of directly with serial
        self.serial_terminal.register_line_received_callback(self.update_graphs)
        
        # Create thread to draw graphs
        self.draw_graphs_thread = threading.Thread(target=self.draw_graphs, daemon=True)
        self.draw_graphs_thread.start()

    def setup_ui(self) -> None:
        # Create a frame to hold graphs and options
        self.graphs_frame = tk.Frame(master=self.master, bg="#E0E8F0")
        self.graphs_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        
        # Create figure to draw accelerometer data
        self.accelerometer_figure = tkPlotGraph(
            master=self.graphs_frame,
            title="Linear Acceleration (G)",
            max_samples=GRAPH_MAX_SAMPLES,
        )
        self.accelerometer_figure.grid(row=0, column=0, padx=2)
        self.accelerometer_figure.set_ylim(
            low=-GRAPH_ACCEL_Y_LIMIT, high=GRAPH_ACCEL_Y_LIMIT
        )
        
        # Create figure to draw gyroscope data
        self.gyroscope_figure = tkPlotGraph(
            master=self.graphs_frame,
            title="Euler Angle (Degree)",
            max_samples=GRAPH_MAX_SAMPLES,
        )
        self.gyroscope_figure.grid(row=0, column=1, padx=2)
        self.gyroscope_figure.set_ylim(low=-GRAPH_GYRO_Y_LIMIT, high=GRAPH_GYRO_Y_LIMIT)
        
        # Create a frame containing options (will hold buttons frame)
        self.options_frame = tk.Frame(master=self.graphs_frame)
        self.options_frame.grid(row=0, column=2, sticky="ew", padx=(2, 2))
        
        # Create show/hide IMU data button (in its own frame within options)
        self.imu_toggle_frame = tk.Frame(master=self.options_frame)
        self.imu_toggle_frame.grid(row=0, column=0, sticky="w")
        
        self.imu_data_toggle_button = tk.Button(
            master=self.imu_toggle_frame,
            text="Hide IMU data",
            command=self.toggle_imu_data,
        )
        self.imu_data_toggle_button.config(width=20)
        self.imu_data_toggle_button.grid(row=0, column=0, padx=2, pady=2)

    def get_buttons_frame(self) -> tk.Frame:
        """Get the frame where external buttons should be added."""
        return self.options_frame

    def toggle_imu_data(self) -> None:
        self.show_imu_data = not self.show_imu_data
        display_text = "Hide IMU data" if self.show_imu_data else "Show IMU data"
        self.imu_data_toggle_button.configure(text=display_text)

    def update_graphs(self, reading: str) -> None:
        match = re.search(SERIAL_IMU_BNO085_DATA_REGEX, reading)
        if match:
            groups = match.groups()
            
            if len(groups) == 7:
                time_group = groups[0]
                acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z = groups[1:]
            else:
                time_group = None
                acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z = groups
            
            if time_group is None:
                try:
                    time_val = int(datetime.now().timestamp() * 1000)
                except Exception:
                    time_val = 0
            else:
                try:
                    time_val = int(time_group)
                except Exception:
                    time_val = int(datetime.now().timestamp() * 1000)
            
            accelerometer_data = {
                "x-axis": float(acc_x),
                "y-axis": float(acc_y),
                "z-axis": float(acc_z),
            }
            self.accelerometer_figure.append_dict(int(time_val), accelerometer_data)
            
            gyroscope_data = {
                "x-axis": float(gyro_x),
                "y-axis": float(gyro_y),
                "z-axis": float(gyro_z),
            }
            self.gyroscope_figure.append_dict(int(time_val), gyroscope_data)

    def reset_graphs(self) -> None:
        self.accelerometer_figure.clear()
        self.gyroscope_figure.clear()

    def draw_graphs(self) -> None:
        while not self.stop_event.is_set():
            if self.stop_event.wait(THREAD_PLOTTER_DRAW_GRAPH_INTERVAL):
                break
            
            try:
                if self.accelerometer_figure.data_modified:
                    self.accelerometer_figure.draw()
                if self.gyroscope_figure.data_modified:
                    self.gyroscope_figure.draw()
            except RuntimeError:
                pass
            except Exception:
                pass

    def close(self) -> None:
        self.killed = True
        self.stop_event.set()
