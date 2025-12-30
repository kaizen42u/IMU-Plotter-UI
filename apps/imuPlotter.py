"""IMU Plotter module for displaying accelerometer and gyroscope data."""

import re
import threading
import tkinter as tk
from datetime import datetime

import matplotlib
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

from mpl_toolkits.mplot3d.art3d import Poly3DCollection
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
SERIAL_IMU_BNO085_DATA_REGEX = r"BNO085\s*\[\s*(\d+)\s*ms\]\s*\|\s*Yaw:\s*([-+]?\d+(?:\.\d+)?)°\s*Pitch:\s*([-+]?\d+(?:\.\d+)?)°\s*Roll:\s*([-+]?\d+(?:\.\d+)?)°\s*\|\s*X\s*Accel:\s*([-+]?\d+(?:\.\d+)?)\s*m/s²\s*Y\s*Accel:\s*([-+]?\d+(?:\.\d+)?)\s*m/s²\s*Z\s*Accel:\s*([-+]?\d+(?:\.\d+)?)\s*m/s²"


class IMUPlotter:
    """Handles IMU data plotting (accelerometer and gyroscope graphs)."""

    def __init__(
        self, master: tk.Tk | tk.Frame, serial_terminal: SerialTerminal
    ) -> None:
        self.master: tk.Tk | tk.Frame = master
        self.serial_terminal: SerialTerminal = serial_terminal
        self.killed: bool = False
        self.stop_event = threading.Event()
        self.show_imu_data: bool = True

        # Store current Euler angles for 3D visualization
        self.current_yaw: float = 0.0
        self.current_pitch: float = 0.0
        self.current_roll: float = 0.0

        # Store angle offsets for nulling
        self.yaw_offset: float = 0.0
        self.pitch_offset: float = 0.0
        self.roll_offset: float = 0.0
        self.nulling_enabled: bool = False

        self.setup_ui()

        # Register callback with SerialTerminal instead of directly with serial
        self.serial_terminal.register_line_received_callback(self.update_graphs)

        # Create thread to draw graphs
        self.draw_graphs_thread = threading.Thread(target=self.draw_graphs, daemon=True)
        self.draw_graphs_thread.start()

    def setup_ui(self) -> None:
        # Create a frame to hold graphs and options
        self.graphs_frame = tk.Frame(master=self.master, bg="#E0E8F0")
        self.graphs_frame.grid(
            row=0, column=0, columnspan=2, sticky="nsew", padx=5, pady=5
        )

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

        # Create 3D visualization for Euler angles
        self.create_3d_visualization()

        # Create figure to draw gyroscope data
        self.gyroscope_figure = tkPlotGraph(
            master=self.graphs_frame,
            title="Euler Angle (Degree)",
            max_samples=GRAPH_MAX_SAMPLES,
        )
        self.gyroscope_figure.grid(row=0, column=2, padx=2)
        self.gyroscope_figure.set_ylim(low=-GRAPH_GYRO_Y_LIMIT, high=GRAPH_GYRO_Y_LIMIT)

        # Create a frame containing options (will hold buttons frame)
        self.options_frame = tk.Frame(master=self.graphs_frame)
        self.options_frame.grid(row=0, column=3, sticky="ew", padx=(2, 2))

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

        # Create null angles button
        self.null_frame = tk.Frame(master=self.options_frame)
        self.null_frame.grid(row=1, column=0, sticky="w")

        self.null_button = tk.Button(
            master=self.null_frame,
            text="Null Angles",
            command=self.null_angles,
        )
        self.null_button.config(width=20)
        self.null_button.grid(row=0, column=0, padx=2, pady=2)

    def create_3d_visualization(self) -> None:
        """Create 3D visualization frame with cube and axes."""
        self.visualization_frame = tk.Frame(master=self.graphs_frame, bg="white")
        self.visualization_frame.grid(row=0, column=1, padx=2, sticky="nsew")

        # Create matplotlib figure for 3D plot
        self.fig_3d = Figure(figsize=(5, 5), dpi=100)
        self.ax_3d = self.fig_3d.add_subplot(111, projection="3d")

        # Set viewpoint 30 degrees higher, aligned with Y axis
        self.ax_3d.view_init(elev=30, azim=0)

        # Draw initial cube and axes
        self.draw_3d_visualization()

        # Embed the figure in tkinter
        self.canvas_3d = FigureCanvasTkAgg(self.fig_3d, master=self.visualization_frame)
        self.canvas_3d.get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def draw_3d_visualization(self) -> None:
        """Draw 3D cube with rotated axes based on Euler angles."""
        self.ax_3d.clear()

        # Create cube vertices (longer on X axis - red)
        cube_x = 1.5  # Longer on X axis
        cube_y = 1.0
        cube_z = 1.0
        cube_vertices = np.array(
            [
                [-cube_x, -cube_y, -cube_z],
                [cube_x, -cube_y, -cube_z],
                [cube_x, cube_y, -cube_z],
                [-cube_x, cube_y, -cube_z],
                [-cube_x, -cube_y, cube_z],
                [cube_x, -cube_y, cube_z],
                [cube_x, cube_y, cube_z],
                [-cube_x, cube_y, cube_z],
            ]
        )

        # Rotate cube based on Euler angles (yaw, pitch, roll)
        yaw_rad = np.radians(self.current_yaw)
        pitch_rad = np.radians(self.current_pitch)
        roll_rad = np.radians(self.current_roll)

        # Rotation matrices
        R_yaw = np.array(
            [
                [np.cos(yaw_rad), -np.sin(yaw_rad), 0],
                [np.sin(yaw_rad), np.cos(yaw_rad), 0],
                [0, 0, 1],
            ]
        )

        R_pitch = np.array(
            [
                [np.cos(pitch_rad), 0, np.sin(pitch_rad)],
                [0, 1, 0],
                [-np.sin(pitch_rad), 0, np.cos(pitch_rad)],
            ]
        )

        R_roll = np.array(
            [
                [1, 0, 0],
                [0, np.cos(roll_rad), -np.sin(roll_rad)],
                [0, np.sin(roll_rad), np.cos(roll_rad)],
            ]
        )

        # Apply rotations (ZYX order - yaw, pitch, roll)
        R = R_yaw @ R_pitch @ R_roll
        rotated_vertices = cube_vertices @ R.T

        # Define cube faces with colors (each face is a list of 4 vertex indices)
        faces = [
            ([0, 1, 2, 3], "cyan", 1.0),  # Bottom face
            ([4, 5, 6, 7], "blue", 1.0),  # Top face
            ([0, 1, 5, 4], "yellow", 1.0),  # Front face
            ([2, 3, 7, 6], "green", 1.0),  # Back face
            ([0, 3, 7, 4], "magenta", 1.0),  # Left face
            ([1, 2, 6, 5], "red", 1.0),  # Right face
        ]

        # Calculate depth (Z-coordinate) for each face to sort by drawing order
        face_depths = []
        for face_indices, color, alpha in faces:
            face_vertices = rotated_vertices[face_indices]
            # Calculate average Z depth of the face
            avg_depth = np.mean(face_vertices[:, 2])
            face_depths.append((avg_depth, face_indices, color, alpha))

        # Sort faces by depth (nearest last for proper occlusion)
        face_depths.sort(key=lambda x: x[0])

        # Draw filled cube faces
        for avg_depth, face_indices, color, alpha in face_depths:
            face_vertices = rotated_vertices[face_indices]
            face_collection = Poly3DCollection(
                [face_vertices],
                alpha=alpha,
                facecolor=color,
                edgecolor="black",
                linewidth=1.5,
            )
            self.ax_3d.add_collection3d(face_collection)

        # Draw cube edges for definition
        edges = [
            [0, 1],
            [1, 2],
            [2, 3],
            [3, 0],  # Bottom face
            [4, 5],
            [5, 6],
            [6, 7],
            [7, 4],  # Top face
            [0, 4],
            [1, 5],
            [2, 6],
            [3, 7],  # Vertical edges
        ]

        for edge in edges:
            pts = rotated_vertices[edge]
            self.ax_3d.plot3D(*pts.T, "k-", linewidth=1)

        # Draw axes with arrows (smaller, positioned to the side)
        axis_length = 0.6
        axis_origin = np.array([1.8, -1.8, -1.8])  # Position in corner of plot

        # X axis (red)
        x_axis = np.array([axis_length, 0, 0]) @ R.T
        self.ax_3d.quiver(
            axis_origin[0],
            axis_origin[1],
            axis_origin[2],
            x_axis[0],
            x_axis[1],
            x_axis[2],
            color="red",
            arrow_length_ratio=0.3,
            linewidth=2,
            label="X",
        )

        # Y axis (green)
        y_axis = np.array([0, axis_length, 0]) @ R.T
        self.ax_3d.quiver(
            axis_origin[0],
            axis_origin[1],
            axis_origin[2],
            y_axis[0],
            y_axis[1],
            y_axis[2],
            color="green",
            arrow_length_ratio=0.3,
            linewidth=2,
            label="Y",
        )

        # Z axis (blue)
        z_axis = np.array([0, 0, axis_length]) @ R.T
        self.ax_3d.quiver(
            axis_origin[0],
            axis_origin[1],
            axis_origin[2],
            z_axis[0],
            z_axis[1],
            z_axis[2],
            color="blue",
            arrow_length_ratio=0.3,
            linewidth=2,
            label="Z",
        )

        # Set labels and limits
        self.ax_3d.set_xlabel("X")
        self.ax_3d.set_ylabel("Y")
        self.ax_3d.set_zlabel("Z")
        self.ax_3d.set_xlim([-2.5, 2.5])
        self.ax_3d.set_ylim([-2.5, 2.5])
        self.ax_3d.set_zlim([-2.5, 2.5])

        # Hide axis tick labels
        self.ax_3d.set_xticks([])
        self.ax_3d.set_yticks([])
        self.ax_3d.set_zticks([])  # type: ignore

        self.ax_3d.grid(False)
        self.ax_3d.set_title(
            f"Yaw: {self.current_yaw:.1f}° Pitch: {self.current_pitch:.1f}° Roll: {self.current_roll:.1f}°"
        )

    def update_3d_visualization(self) -> None:
        """Update the 3D visualization with new Euler angles."""
        self.draw_3d_visualization()
        self.canvas_3d.draw()

    def get_buttons_frame(self) -> tk.Frame:
        """Get the frame where external buttons should be added."""
        return self.options_frame

    def toggle_imu_data(self) -> None:
        self.show_imu_data = not self.show_imu_data
        display_text = "Hide IMU data" if self.show_imu_data else "Show IMU data"
        self.imu_data_toggle_button.configure(text=display_text)

    def null_angles(self) -> None:
        """Toggle nulling of angles. When enabled, sets current angles as offset."""
        if not self.nulling_enabled:
            # Enable nulling - store current angles as offset
            self.yaw_offset = self.current_yaw
            self.pitch_offset = self.current_pitch
            self.roll_offset = self.current_roll
            self.nulling_enabled = True
            self.null_button.configure(text="Un-Null Angles")
        else:
            # Disable nulling - clear offsets
            self.yaw_offset = 0.0
            self.pitch_offset = 0.0
            self.roll_offset = 0.0
            self.nulling_enabled = False
            self.null_button.configure(text="Null Angles")

    def update_graphs(self, reading: str) -> None:
        match = re.search(SERIAL_IMU_BNO085_DATA_REGEX, reading)
        if match:
            groups = match.groups()

            if len(groups) == 7:
                time_group, gyro_x, gyro_y, gyro_z, acc_x, acc_y, acc_z = groups
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

            # Update Euler angles for 3D visualization (apply offset)
            self.current_yaw = float(gyro_x) - self.yaw_offset
            self.current_pitch = float(gyro_y) - self.pitch_offset
            self.current_roll = float(gyro_z) - self.roll_offset

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

                # Update 3D visualization
                self.update_3d_visualization()
            except RuntimeError:
                pass
            except Exception:
                pass

    def close(self) -> None:
        self.killed = True
        self.stop_event.set()
