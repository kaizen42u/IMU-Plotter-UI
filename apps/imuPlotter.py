"""IMU Plotter module for displaying accelerometer and gyroscope data."""

import threading
import tkinter as tk
from datetime import datetime
from tkinter import ttk

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
GRAPH_TIME_SPAN_MS = config.get("imu.graph_time_span_ms", 3000)
GRAPH_ACCEL_Y_LIMIT = config.get("imu.graph_accel_y_limit", 16)
GRAPH_GYRO_Y_LIMIT = config.get("imu.graph_gyro_y_limit", 200)
THREAD_PLOTTER_DRAW_GRAPH_INTERVAL = config.get("imu.draw_graph_interval", 0.05)

# Event IDs for BNO085 IMU data
EVENT_BNO085_ROTATION_VECTOR = "0x10"
EVENT_BNO085_LINEAR_ACCELERATION = "0x11"


class IMUPlotter:
    """Handles IMU data plotting (accelerometer and gyroscope graphs)."""

    def __init__(
        self, master: tk.Tk | tk.Frame, serial_terminal: SerialTerminal
    ) -> None:
        self.master: tk.Tk | tk.Frame = master
        self.serial_terminal: SerialTerminal = serial_terminal
        self.killed: bool = False
        self.stop_event = threading.Event()

        # Store current Euler angles for 3D visualization
        self.current_yaw: float = 0.0
        self.current_pitch: float = 0.0
        self.current_roll: float = 0.0

        # Store angle offsets for nulling
        self.yaw_offset: float = 0.0
        self.pitch_offset: float = 0.0
        self.roll_offset: float = 0.0
        self.nulling_enabled: bool = False

        # Load BNO085 configuration
        config = get_config_manager()
        self.bno085_tx_gpio = config.get("bno085.tx_gpio", "GPIO5")
        self.bno085_rx_gpio = config.get("bno085.rx_gpio", "GPIO4")
        self.bno085_initialized: bool = False

        self.setup_ui()

        # Register event callbacks with SerialTerminal
        self.serial_terminal.register_event_callback(
            EVENT_BNO085_ROTATION_VECTOR, self.on_rotation_vector_event
        )
        self.serial_terminal.register_event_callback(
            EVENT_BNO085_LINEAR_ACCELERATION, self.on_linear_acceleration_event
        )

        # Register connection state callback to update button states
        self.serial_terminal.register_connection_state_callback(
            self.update_connection_state
        )

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
            max_samples=GRAPH_MAX_SAMPLES if GRAPH_MAX_SAMPLES > 0 else None,
            timespan=GRAPH_TIME_SPAN_MS if GRAPH_TIME_SPAN_MS > 0 else None,
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
            max_samples=GRAPH_MAX_SAMPLES if GRAPH_MAX_SAMPLES > 0 else None,
            timespan=GRAPH_TIME_SPAN_MS if GRAPH_TIME_SPAN_MS > 0 else None,
        )
        self.gyroscope_figure.grid(row=0, column=2, padx=2)
        self.gyroscope_figure.set_ylim(low=-GRAPH_GYRO_Y_LIMIT, high=GRAPH_GYRO_Y_LIMIT)

        # Create a frame containing options (will hold buttons frame)
        self.options_frame = tk.Frame(master=self.graphs_frame)
        self.options_frame.grid(row=0, column=3, sticky="nsew", padx=(2, 2))

        # Create BNO085 configuration frame
        self.create_bno085_config_section()

        # Create tare buttons frame
        self.tare_frame = tk.LabelFrame(
            master=self.options_frame,
            text="Tare",
            font=("Arial", 9, "bold"),
            padx=5,
            pady=5,
        )
        self.tare_frame.grid(row=3, column=0, sticky="w", pady=(10, 0))

        # Tare XYZ button
        self.tare_xyz_button = tk.Button(
            master=self.tare_frame,
            text="Tare XYZ",
            command=lambda: self.send_tare_command("xyz"),
        )
        self.tare_xyz_button.config(width=20)
        self.tare_xyz_button.grid(row=0, column=0, padx=2, pady=2)

        # Tare Z button
        self.tare_z_button = tk.Button(
            master=self.tare_frame,
            text="Tare Z",
            command=lambda: self.send_tare_command("z"),
        )
        self.tare_z_button.config(width=20)
        self.tare_z_button.grid(row=1, column=0, padx=2, pady=2)

        # Tare Clear button
        self.tare_clear_button = tk.Button(
            master=self.tare_frame,
            text="Tare Clear",
            command=lambda: self.send_tare_command("clear"),
        )
        self.tare_clear_button.config(width=20)
        self.tare_clear_button.grid(row=2, column=0, padx=2, pady=2)

    def create_bno085_config_section(self) -> None:
        """Create BNO085 configuration section with GPIO and Init/Deinit buttons."""
        GPIO_OPTIONS: list[str] = [f"GPIO{i}" for i in range(22)] + [
            f"GPIO{i}" for i in range(26, 49)
        ]

        config_frame: tk.LabelFrame = tk.LabelFrame(
            master=self.options_frame,
            text="BNO085 Config",
            font=("Arial", 9, "bold"),
            padx=5,
            pady=5,
        )
        config_frame.grid(row=0, column=0, sticky="w", pady=(0, 5))

        # TX GPIO selection
        tx_frame: tk.Frame = tk.Frame(master=config_frame)
        tx_frame.pack(side=tk.TOP, fill=tk.X, pady=2)

        tx_label: tk.Label = tk.Label(master=tx_frame, text="TX:", width=5, anchor="w")
        tx_label.pack(side=tk.LEFT, padx=2)

        self.bno085_tx_combobox: ttk.Combobox = ttk.Combobox(
            master=tx_frame,
            values=GPIO_OPTIONS,
            state="readonly",
            width=10,
        )
        self.bno085_tx_combobox.set(self.bno085_tx_gpio)
        self.bno085_tx_combobox.pack(side=tk.LEFT, padx=2)

        # RX GPIO selection
        rx_frame: tk.Frame = tk.Frame(master=config_frame)
        rx_frame.pack(side=tk.TOP, fill=tk.X, pady=2)

        rx_label: tk.Label = tk.Label(master=rx_frame, text="RX:", width=5, anchor="w")
        rx_label.pack(side=tk.LEFT, padx=2)

        self.bno085_rx_combobox: ttk.Combobox = ttk.Combobox(
            master=rx_frame,
            values=GPIO_OPTIONS,
            state="readonly",
            width=10,
        )
        self.bno085_rx_combobox.set(self.bno085_rx_gpio)
        self.bno085_rx_combobox.pack(side=tk.LEFT, padx=2)

        # Init/Deinit buttons
        button_frame: tk.Frame = tk.Frame(master=config_frame)
        button_frame.pack(side=tk.TOP, fill=tk.X, pady=(5, 0))

        self.bno085_init_button: tk.Button = tk.Button(
            master=button_frame,
            text="Init",
            command=self.bno085_init,
            width=8,
        )
        self.bno085_init_button.pack(side=tk.LEFT, padx=1)

        self.bno085_deinit_button: tk.Button = tk.Button(
            master=button_frame,
            text="Deinit",
            command=self.bno085_deinit,
            width=8,
        )
        self.bno085_deinit_button.pack(side=tk.LEFT, padx=1)

    def bno085_init(self) -> None:
        """Initialize BNO085 sensor with selected GPIO pins."""
        try:
            if not self.serial_terminal.serial.is_connected():
                print("Serial port not connected")
                return

            # Get selected GPIO values
            self.bno085_tx_gpio = self.bno085_tx_combobox.get()
            self.bno085_rx_gpio = self.bno085_rx_combobox.get()

            # Save configuration
            self._save_bno085_config()

            # Send init command (strip "GPIO" prefix from pin numbers)
            tx_pin = self.bno085_tx_gpio.replace("GPIO", "")
            rx_pin = self.bno085_rx_gpio.replace("GPIO", "")
            command = f"bno085 init {tx_pin} {rx_pin}\n"
            self.serial_terminal.send_command(command)
            self.bno085_initialized = True
            print(
                f"BNO085 initialized with TX={self.bno085_tx_gpio}, RX={self.bno085_rx_gpio}"
            )
        except Exception as e:
            print(f"Error initializing BNO085: {e}")

    def bno085_deinit(self) -> None:
        """Deinitialize BNO085 sensor."""
        try:
            if not self.serial_terminal.serial.is_connected():
                print("Serial port not connected")
                return

            # Send deinit command
            command = "bno085 deinit\n"
            self.serial_terminal.send_command(command)
            self.bno085_initialized = False
            print("BNO085 deinitialized")
        except Exception as e:
            print(f"Error deinitializing BNO085: {e}")

    def _save_bno085_config(self) -> None:
        """Save BNO085 configuration to config file."""
        try:
            config = get_config_manager()
            config.set("bno085.tx_gpio", self.bno085_tx_gpio)
            config.set("bno085.rx_gpio", self.bno085_rx_gpio)
            config.save()
        except Exception as e:
            print(f"Error saving BNO085 config: {e}")

    def update_connection_state(self) -> None:
        """Update button states based on connection state."""
        is_connected = self.serial_terminal.serial.is_connected()
        self.bno085_init_button.config(state="normal" if is_connected else "disabled")
        self.bno085_deinit_button.config(state="normal" if is_connected else "disabled")

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
        pitch_rad = np.radians(-self.current_pitch)  # Invert pitch for visual
        roll_rad = np.radians(-self.current_roll)  # Invert roll for visual

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

    def send_tare_command(self, axes: str) -> None:
        """Send tare command to BNO085 sensor.
        
        Args:
            axes: Axes to tare - 'xyz', 'z', or 'clear'
        """
        if not self.bno085_initialized:
            print("BNO085 not initialized. Please initialize first.")
            return
        
        command = f"bno085 tare {axes}"
        self.serial_terminal.send_command_entry.delete(0, tk.END)
        self.serial_terminal.send_command_entry.insert(0, command)
        self.serial_terminal.send_command()

    def on_rotation_vector_event(self, timestamp: str, data: str) -> None:
        """Callback for rotation vector event (0x10).

        Data format: "<yaw> <pitch> <roll>" (three float values in degrees)
        Timestamp format: "       15765 ms"
        """
        try:
            # Parse the three float values
            values = data.split()
            if len(values) >= 3:
                yaw = float(values[0])
                pitch = float(values[1])
                roll = float(values[2])

                # Update Euler angles for 3D visualization (apply offset)
                self.current_yaw = yaw - self.yaw_offset
                self.current_pitch = pitch - self.pitch_offset
                self.current_roll = roll - self.roll_offset

                # Extract timestamp in milliseconds
                try:
                    ts_str = timestamp.strip().split()[0]
                    time_val = int(float(ts_str))
                except (ValueError, IndexError):
                    time_val = int(datetime.now().timestamp() * 1000)

                # Add to gyroscope graph
                gyroscope_data = {
                    "x-axis": yaw,
                    "y-axis": pitch,
                    "z-axis": roll,
                }
                self.gyroscope_figure.append_dict(time_val, gyroscope_data)
        except Exception as e:
            print(f"Error processing rotation vector event: {e}")

    def on_linear_acceleration_event(self, timestamp: str, data: str) -> None:
        """Callback for linear acceleration event (0x11).

        Data format: "<acc_x> <acc_y> <acc_z>" (three float values in m/s²)
        Timestamp format: "       15765 ms"
        """
        try:
            # Parse the three float values
            values = data.split()
            if len(values) >= 3:
                acc_x = float(values[0])
                acc_y = float(values[1])
                acc_z = float(values[2])

                # Extract timestamp in milliseconds
                try:
                    ts_str = timestamp.strip().split()[0]
                    time_val = int(float(ts_str))
                except (ValueError, IndexError):
                    time_val = int(datetime.now().timestamp() * 1000)

                # Add to accelerometer graph
                accelerometer_data = {
                    "x-axis": acc_x,
                    "y-axis": acc_y,
                    "z-axis": acc_z,
                }
                self.accelerometer_figure.append_dict(time_val, accelerometer_data)
        except Exception as e:
            print(f"Error processing linear acceleration event: {e}")

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
