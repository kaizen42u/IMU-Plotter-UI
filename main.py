import re
import threading
import tkinter as tk
from tkinter import ttk
from typing import cast
from datetime import datetime
from typing import List
from pathlib import Path

import matplotlib
import serial

from serialHandler import serialHandler
from ansiEncoding import ANSI

from tkAutocompleteCombobox import tkAutocompleteCombobox
from tkPlotGraph import tkPlotGraph
from tkTerminal import tkTerminal

matplotlib.use("Agg")


TERMINAL_MAX_WIDTH = 180
GRAPH_MAX_SAMPLES = 50
GRAPH_ACCEL_Y_LIMIT = 16
GRAPH_GYRO_Y_LIMIT = 200
SERIAL_IMU_BNO085_DATA_REGEX = r"(?:I\s*\(\s*(\d+)\s*\)\s*\w+:\s*)?L\.Accel\s*\(m/s\)\s*-\s*x:\s*([-+]?\d+(?:\.\d+)?)\s*y:\s*([-+]?\d+(?:\.\d+)?)\s*z:\s*([-+]?\d+(?:\.\d+)?)\s*\|\s*Euler\s*\(deg\)\s*-\s*yaw:\s*([-+]?\d+(?:\.\d+)?)\s*pitch:\s*([-+]?\d+(?:\.\d+)?)\s*roll:\s*([-+]?\d+(?:\.\d+)?)"
THREAD_PLOTTER_DRAW_GRAPH_INTERVAL = 0.05


class SerialPlotterApp:

    def __init__(self, master: tk.Tk) -> None:
        self.master: tk.Tk = master
        self.killed: bool = False
        self.stop_event = threading.Event()
        self.show_imu_data: bool = True

        self._reconnect_enabled: bool = (
            False  # Only enabled after manual connect, disabled on manual disconnect
        )
        self._reconnect_attempts: int = 0

        # Logging variables
        self.logging_enabled: bool = False
        self.log_file_path: Path | None = None
        self.log_file_handle = None

        self.serial: serialHandler = serialHandler()

        self.setup_ui()

        # Enable logging by default
        self.logging_var.set(True)
        self.start_logging()

        # Get a list of all available serial ports
        ports = self.serial.get_ports()
        self.port_selection_combobox.set_completion_list(ports)
        self.serial_connect_toggle_button_update()

        self.serial.set_line_received_callback(self.serial_line_received)
        self.serial.set_log_callback(self.serial_log)
        self.serial.set_ports_changed_callback(self.serial_ports_changed)
        self.serial.set_disconnect_callback(self.serial_disconnected)

        # Create thread to draw graphs
        self.draw_graphs_thread = threading.Thread(target=self.draw_graphs, daemon=True)
        self.draw_graphs_thread.start()

    def setup_ui(self) -> None:

        # Create a main control frame to group all top controls
        self.control_frame = tk.Frame(master=self.master)
        self.control_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)

        # Create a label for COM port selection
        self.port_selection_label = tk.Label(
            master=self.control_frame, text="COM Port:"
        )
        self.port_selection_label.grid(row=0, column=0, padx=5)

        # Create a dropdown menu for available ports
        self.port_selection_combobox = tkAutocompleteCombobox(
            master=self.control_frame, state="readonly"
        )
        self.port_selection_combobox.grid(row=0, column=1, padx=(5, 15))

        # Create a label for baudrate selection
        self.baudrate_label = tk.Label(master=self.control_frame, text="Baudrate:")
        self.baudrate_label.grid(row=0, column=2, padx=5)

        # Create a dropdown menu for baudrate selection, read write, default 115200
        self.baudrate_combobox = tkAutocompleteCombobox(
            master=self.control_frame, sort_key=lambda x: int(x)
        )
        common_baudrates = [
            "9600",
            "14400",
            "19200",
            "38400",
            "57600",
            "115200",
            "230400",
            "460800",
            "921600",
        ]
        self.baudrate_combobox.set_completion_list(common_baudrates)
        self.baudrate_combobox.set("115200")
        self.baudrate_combobox.grid(row=0, column=3, padx=(5, 15))

        # Create serial connect/disconnect button
        self.serial_connect_toggle_button = tk.Button(
            master=self.control_frame, text="null", command=self.serial_connect_toggle
        )
        self.serial_connect_toggle_button.config(width=20)
        self.serial_connect_toggle_button.grid(row=0, column=4, padx=5)

        # Create terminal auto scroll checkbox
        self.terminal_auto_scroll_var = tk.BooleanVar(master=self.master, value=True)
        self.terminal_auto_scroll_checkbox = tk.Checkbutton(
            master=self.control_frame,
            text="Auto Scroll",
            variable=self.terminal_auto_scroll_var,
            command=lambda: self.terminal.set_autoscroll(
                self.terminal_auto_scroll_var.get()
            ),
        )
        self.terminal_auto_scroll_checkbox.config(width=20)
        self.terminal_auto_scroll_checkbox.grid(row=0, column=5, padx=5)

        # Create logging checkbox
        self.logging_var = tk.BooleanVar(master=self.master, value=True)
        self.logging_checkbox = tk.Checkbutton(
            master=self.control_frame,
            text="Logging",
            variable=self.logging_var,
            command=self.toggle_logging,
        )
        self.logging_checkbox.config(width=20)
        self.logging_checkbox.grid(row=0, column=6, padx=5)

        # Create the serial terminal
        self.terminal = tkTerminal(master=self.master, width=TERMINAL_MAX_WIDTH)
        self.terminal.grid(row=1, column=0, sticky="ns", padx=5)

        # Create a frame for the send command section
        self.send_command_frame = tk.Frame(master=self.master)
        self.send_command_frame.grid(row=2, column=0, sticky="ew", padx=5, pady=5)
        self.send_command_frame.grid_columnconfigure(1, weight=1)

        # Create a label for the send command textfield
        self.send_command_label = tk.Label(
            master=self.send_command_frame, text="Send Command:"
        )
        self.send_command_label.grid(row=0, column=0, padx=5)

        # Create a textfield for sending commands
        self.send_command_entry = tk.Entry(master=self.send_command_frame)
        self.send_command_entry.grid(row=0, column=1, sticky="ew", padx=5)

        # Bind Enter key to send command
        self.send_command_entry.bind("<Return>", lambda event: self.send_command())

        # Create a send button
        self.send_command_button = tk.Button(
            master=self.send_command_frame, text="Send", command=self.send_command
        )
        self.send_command_button.grid(row=0, column=2, padx=5)

        # Create a frame to hold graphs and options
        self.graphs_frame = tk.Frame(master=self.master, bg="#E0E8F0")
        self.graphs_frame.grid(row=3, column=0, sticky="ew", padx=5)
        # self.graphs_frame.grid_columnconfigure(0, weight=1)
        # self.graphs_frame.grid_columnconfigure(1, weight=1)

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

        # Create a frame containing options
        self.options_frame = tk.Frame(master=self.graphs_frame)
        self.options_frame.grid_rowconfigure(index=0, weight=1)
        self.options_frame.grid(row=0, column=2, sticky="ew", padx=(2, 2))

        # Create a frame for buttons
        self.buttons_frame = tk.Frame(master=self.options_frame)
        self.buttons_frame.grid(row=0, column=0, sticky="w")

        # Create show/hide IMU data button
        self.imu_data_toggle_button = tk.Button(
            master=self.buttons_frame,
            text="Hide IMU data",
            command=self.imu_data_toggle,
        )
        self.imu_data_toggle_button.config(width=20)
        self.imu_data_toggle_button.grid(row=0, column=0, padx=2, pady=2)

        # Create ESCs button
        self.escs_button = tk.Button(
            master=self.buttons_frame,
            text="ESCs",
            command=self.open_esc_control,
        )
        self.escs_button.config(width=20)
        self.escs_button.grid(row=1, column=0, padx=2, pady=2)

        # Create Lights button
        self.lights_button = tk.Button(
            master=self.buttons_frame,
            text="Lights",
            command=self.open_light_control,
        )
        self.lights_button.config(width=20)
        self.lights_button.grid(row=2, column=0, padx=2, pady=2)

        # Configure the grid to expand
        self.master.grid_rowconfigure(1, weight=1)
        self.master.grid_columnconfigure(0, weight=1)

    def toggle_logging(self) -> None:
        if self.logging_var.get():
            self.start_logging()
        else:
            self.stop_logging()

    def start_logging(self) -> None:
        try:
            session_logs_dir = Path("./session_logs")
            session_logs_dir.mkdir(exist_ok=True)

            # Create log filename with current timestamp
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file_path = session_logs_dir / f"{timestamp}.log"

            # Open log file for writing
            self.log_file_handle = open(self.log_file_path, "w")
            self.logging_enabled = True
            self.terminal_show_message(
                f"{ANSI.bGreen}Logging started: {self.log_file_path}{ANSI.default}"
            )
        except Exception as e:
            self.terminal_show_message(
                f"{ANSI.bRed}Failed to start logging: {e}{ANSI.default}"
            )
            self.logging_var.set(False)

    def stop_logging(self) -> None:
        """Stop logging and close log file."""
        try:
            if self.log_file_handle:
                self.log_file_handle.close()
            self.logging_enabled = False
            self.log_file_handle = None
            self.terminal_show_message(f"{ANSI.bGreen}Logging stopped{ANSI.default}")
        except Exception as e:
            self.terminal_show_message(
                f"{ANSI.bRed}Failed to stop logging: {e}{ANSI.default}"
            )

    def write_log(self, data: str, direction: str) -> None:
        """Write data to session log. direction should be 'tx' or 'rx'."""
        if not self.logging_enabled or not self.log_file_handle:
            return

        try:
            # Get current time with milliseconds
            now = datetime.now()
            timestamp = now.strftime("%y%m%d-%H%M%S")
            ms = now.microsecond // 1000

            # Remove newlines for cleaner log format
            clean_data = data.rstrip("\n\r")

            # Write to log file
            log_line = f"({timestamp}.{ms:03d})({direction}) | {clean_data}\n"
            self.log_file_handle.write(log_line)
            self.log_file_handle.flush()
        except Exception as e:
            print(f"[W] Error writing to log: {e}")

    def close(self) -> None:
        # Stop logging if active
        if self.logging_enabled:
            self.stop_logging()

        # Flag the process as dead and close serial port
        self.killed = True
        self.stop_event.set()
        self.serial.close()

    def serial_line_received(self, line: str) -> None:
        self.update_graphs(line)
        self.update_terminal(line)

        # Log asynchronously to not block graph/terminal updates
        if self.logging_enabled:
            threading.Thread(
                target=self.write_log, args=(line, " R"), daemon=True
            ).start()

    def serial_log(self, message: str) -> None:
        self.terminal_show_message(message)

    def serial_ports_changed(self, ports: List[str]) -> None:
        self.port_selection_combobox.set_completion_list(
            list(set(self.port_selection_combobox.get_completion_list() + ports))
        )
        # Update button state in case of disconnect callback
        self.serial_connect_toggle_button_update()
        print(f"Ports changed: {ports}")

        # Check if previously selected port came back online and trigger reconnect
        selected_port = self.port_selection_combobox.get()
        if (
            self._reconnect_enabled
            and selected_port
            and selected_port in ports
            and not self.serial.is_connected()
        ):
            self.master.after(100, self.attempt_reconnect)

    def serial_disconnected(self, port: str) -> None:
        self.serial_connect_toggle_button_update()
        if self._reconnect_enabled:
            self.master.after(100, self.attempt_reconnect)

    def attempt_reconnect(self) -> None:
        selected_port = self.port_selection_combobox.get()
        current_ports = self.serial.get_ports()

        if (
            selected_port
            and selected_port in current_ports
            and not self.serial.is_connected()
        ):
            try:
                print(f"Attempting auto-reconnect to {selected_port}...")
                baudrate_str = self.baudrate_combobox.get()
                baudrate = int(baudrate_str) if baudrate_str else 115200
                self.serial.connect(selected_port, baudrate=baudrate)
                self.serial_connect_toggle_button_update()
                print(f"Auto-reconnected to {selected_port}")
                self._reconnect_attempts = 0
            except Exception as e:
                self._reconnect_attempts += 1
                print(
                    f"Auto-reconnect failed (attempt {self._reconnect_attempts}): {e}"
                )
                if self._reconnect_attempts < 5:
                    self.master.after(100, self.attempt_reconnect)
                else:
                    print(
                        f"Auto-reconnect failed after 5 attempts. Manual reconnection required."
                    )
                    self._reconnect_attempts = 0

    def serial_connect_toggle_button_update(self) -> None:
        display_text = "Disconnect" if self.serial.is_connected() else "Connect"
        self.serial_connect_toggle_button.configure(text=display_text)

        # Disable/enable COM port and baudrate selection based on connection state
        is_connected = self.serial.is_connected()
        self.port_selection_combobox.configure(
            state="disabled" if is_connected else "readonly"
        )
        self.baudrate_combobox.configure(state="disabled" if is_connected else "normal")

        # Update ESC control button state
        if hasattr(self, "esc_control_app") and self.esc_control_app is not None:
            self.esc_control_app.update_esc_controls_state()

        # Update Light control button state
        if hasattr(self, "light_control_app") and self.light_control_app is not None:
            self.light_control_app.update_light_controls_state()

    def serial_connect_toggle(self) -> None:
        # If already connected, disconnect
        if self.serial.is_connected():
            self.serial.disconnect()
            self._reconnect_enabled = (
                False  # Disable auto-reconnect on manual disconnect
            )
            self.serial_connect_toggle_button_update()
            print("Auto-reconnect disabled (manual disconnect)")
            return

        # Otherwise, try to connect
        self.reset_graphs()
        try:
            # Get baudrate from combobox, default to 115200 if not set
            baudrate_str = self.baudrate_combobox.get()
            baudrate = int(baudrate_str) if baudrate_str else 115200

            self.serial.connect(self.port_selection_combobox.get(), baudrate=baudrate)
            self._reconnect_enabled = (
                True  # Enable auto-reconnect on successful manual connect
            )
            self._reconnect_attempts = 0  # Reset attempt counter
            self.serial_connect_toggle_button_update()
            print("Auto-reconnect enabled")

        except ValueError:
            self.terminal_show_message(
                f"Invalid baudrate: {self.baudrate_combobox.get()}"
            )
        except serial.SerialException as e:
            self.terminal_show_message(
                f"Could not open port [{self.port_selection_combobox.get()}]: {e}"
            )

    def imu_data_toggle(self) -> None:
        self.show_imu_data = not self.show_imu_data
        display_text = "Hide IMU data" if self.show_imu_data else "Show IMU data"
        self.imu_data_toggle_button.configure(text=display_text)

    def open_esc_control(self) -> None:
        """Toggle ESC control window visibility."""
        if not hasattr(self, "esc_control_app") or self.esc_control_app is None:
            self.esc_control_app = ESCControlApp(parent=self)
        else:
            # Toggle visibility
            if self.esc_control_app.window.winfo_viewable():
                self.esc_control_app.window.withdraw()
            else:
                self.esc_control_app.window.deiconify()

    def open_light_control(self) -> None:
        """Toggle Light control window visibility."""
        if not hasattr(self, "light_control_app") or self.light_control_app is None:
            self.light_control_app = LightControlApp(parent=self)
        else:
            # Toggle visibility
            if self.light_control_app.window.winfo_viewable():
                self.light_control_app.window.withdraw()
            else:
                self.light_control_app.window.deiconify()

    def update_terminal(self, reading: str) -> None:
        is_imu_data: bool = bool(re.search(SERIAL_IMU_BNO085_DATA_REGEX, reading))
        if is_imu_data and not self.show_imu_data:
            return

        self.terminal.write(reading + "\n")

    def update_graphs(self, reading: str) -> None:
        match = re.search(SERIAL_IMU_BNO085_DATA_REGEX, reading)
        if match:
            groups = match.groups()

            # groups layout: (optional_time, acc_x, acc_y, acc_z, yaw, pitch, roll)
            # optional_time may be None if the prefix is not present
            if len(groups) == 7:
                time_group = groups[0]
                acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z = groups[1:]
            else:
                # unexpected group count — fall back to using all groups as values
                time_group = None
                acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z = groups

            # Use provided time if present, otherwise use current epoch milliseconds
            if time_group is None:
                try:
                    time_val = int(datetime.now().timestamp() * 1000)
                except Exception:
                    time_val = 0
            else:
                # Some logs include timestamps like 110322 (ms). Cast to int.
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

    def send_command(self) -> None:
        """Send the command entered in the textfield over the serial port."""
        command = self.send_command_entry.get()
        if not command:
            return

        if not self.serial.is_connected():
            self.terminal_show_message(
                f"{ANSI.bRed}Error: Serial port is not connected{ANSI.default}"
            )
            return

        # Append newline if not already present
        if not command.endswith("\n"):
            command += "\n"

        success = self.serial.send(command)

        if success:
            threading.Thread(
                target=self._async_log_and_display, args=(command, True), daemon=True
            ).start()
        else:
            self.terminal_show_message(
                f"{ANSI.bRed}Error: Failed to send command{ANSI.default}"
            )

        # Keep textfield populated but select all text for quick resend
        self.send_command_entry.select_range(0, tk.END)
        self.send_command_entry.focus()

    def _async_log_and_display(self, command: str, is_tx: bool) -> None:
        try:
            if is_tx:
                self.write_log(command, "T ")

            self.master.after(
                0,
                lambda: self.terminal_show_message(
                    f"{ANSI.bGreen}> {command.rstrip()}{ANSI.default}"
                ),
            )
        except Exception as e:
            print(f"[W] Error in async_log_and_display: {e}")

    def draw_graphs(self) -> None:
        while not self.stop_event.is_set():
            # Use wait() return value to break immediately if stop_event is set
            if self.stop_event.wait(THREAD_PLOTTER_DRAW_GRAPH_INTERVAL):
                break

            # Update graph only if data was modified to reduce CPU usage
            try:
                if self.accelerometer_figure.data_modified:
                    self.accelerometer_figure.draw()
                if self.gyroscope_figure.data_modified:
                    self.gyroscope_figure.draw()
            except RuntimeError:
                pass
            except Exception:
                pass

    def terminal_show_message(self, message: str) -> None:
        self.terminal.write(f"{ANSI.bBrightMagenta}{message}{ANSI.default} \n")
        print(message)


class ESCControlApp:
    # GPIO options from GPIO0-GPIO21 and GPIO26-GPIO48
    GPIO_OPTIONS: list[str] = [f"GPIO{i}" for i in range(22)] + [
        f"GPIO{i}" for i in range(26, 49)
    ]
    FREQUENCY_OPTIONS: list[str] = ["50Hz", "100Hz", "200Hz", "300Hz"]
    DIRECTION_OPTIONS: list[str] = ["Normal", "Inverted"]

    # Default ESC configuration
    DEFAULT_ESC_CONFIG: list[dict[str, str | list[int]]] = [
        {
            "gpio": "GPIO9",
            "direction": "Normal",
            "calibration": [1000, 1442, 1500, 1586, 2000],
        },  # ESC 1
        {
            "gpio": "GPIO10",
            "direction": "Inverted",
            "calibration": [1000, 1444, 1500, 1551, 2000],
        },  # ESC 2
        {
            "gpio": "GPIO11",
            "direction": "Normal",
            "calibration": [1000, 1440, 1500, 1556, 2000],
        },  # ESC 3
        {
            "gpio": "GPIO12",
            "direction": "Inverted",
            "calibration": [1000, 1492, 1500, 1514, 2000],
        },  # ESC 4
    ]

    def __init__(self, parent: SerialPlotterApp) -> None:
        self.parent: SerialPlotterApp = parent
        self.window: tk.Toplevel = tk.Toplevel(parent.master)
        self.window.title("ESC Control")
        self.window.geometry("700x820")

        # Handle window close to hide instead of destroy
        self.window.protocol("WM_DELETE_WINDOW", self.on_window_close)

        # Store ESC configurations with defaults
        self.esc_configs: list[dict[str, str | list[int]]] = [
            self.DEFAULT_ESC_CONFIG[i].copy() for i in range(4)
        ]

        # Create main frame with scrollbar
        main_frame: tk.Frame = tk.Frame(master=self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Initialize widget storage
        self.esc_gpio_comboboxes: list[ttk.Combobox | None] = [None] * 4
        self.esc_direction_comboboxes: list[ttk.Combobox | None] = [None] * 4
        self.esc_initialized: list[bool] = [False] * 4  # Track initialization state
        self.esc_selected: list[tk.BooleanVar] = [
            tk.BooleanVar(value=True) for _ in range(4)
        ]  # Track selected state (default selected)
        self.esc_calibration_entries: list[list[tk.Entry]] = []
        self.esc_power_sliders: list[tk.Scale] = []
        self.esc_power_value_labels: list[tk.Label] = []

        # Initialize power slider throttling (only send latest value at timed intervals)
        self.esc_power_pending: list[float | None] = [
            None
        ] * 4  # Store pending power values
        self.esc_power_send_scheduled: list[bool] = [
            False
        ] * 4  # Track if send is already scheduled

        # Create common settings section
        self._create_common_section(main_frame)

        # Create 4 ESC sections
        for esc_id in range(1, 5):
            self._create_esc_section(main_frame, esc_id - 1, esc_id)

    def _create_common_section(self, parent: tk.Frame) -> None:
        """Create a common settings section for all ESCs."""
        common_frame: tk.LabelFrame = tk.LabelFrame(
            master=parent,
            text="Common Settings",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10,
        )
        common_frame.pack(fill=tk.X, pady=5)

        # Frequency selection and Init button on same line
        settings_frame: tk.Frame = tk.Frame(master=common_frame)
        settings_frame.pack(fill=tk.X, pady=5)

        # Frequency frame (left)
        freq_frame: tk.Frame = tk.Frame(master=settings_frame)
        freq_frame.pack(side=tk.LEFT, padx=5)

        freq_label: tk.Label = tk.Label(
            master=freq_frame, text="Frequency:", anchor="w"
        )
        freq_label.pack(side=tk.LEFT, padx=2)

        self.frequency_combobox: ttk.Combobox = ttk.Combobox(
            master=freq_frame,
            values=self.FREQUENCY_OPTIONS,
            state="readonly",
            width=12,
        )
        self.frequency_combobox.set("50Hz")
        self.frequency_combobox.pack(side=tk.LEFT, padx=2)

        # Init and Deinit buttons frame (right)
        button_frame: tk.Frame = tk.Frame(master=settings_frame)
        button_frame.pack(side=tk.RIGHT, padx=5)

        self.init_escs_button: tk.Button = tk.Button(
            master=button_frame,
            text="Init ESCs",
            command=self.init_escs,
            width=12,
        )
        self.init_escs_button.pack(side=tk.LEFT, padx=2)

        self.deinit_escs_button: tk.Button = tk.Button(
            master=button_frame,
            text="Deinit ESCs",
            command=self.deinit_escs,
            width=12,
        )
        self.deinit_escs_button.pack(side=tk.LEFT, padx=2)

        # Update button state based on serial connection
        self.update_esc_controls_state()

    def on_window_close(self) -> None:
        """Hide window instead of closing it."""
        self.window.withdraw()

    def init_escs(self) -> None:
        """Send init commands for enabled ESCs that haven't been initialized yet."""
        command_delay = 0

        for index in range(4):
            esc_id = index + 1
            # Skip deselected ESCs
            if not self.esc_selected[index].get():
                print(f"ESC {esc_id} is not selected, skipping init")
                continue

            # Skip already initialized ESCs
            if self.esc_initialized[index]:
                print(f"ESC {esc_id} is already initialized, skipping init")
                continue

            if self.esc_gpio_comboboxes[index] is None:
                print(f"Error: ESC {esc_id} GPIO combobox is not initialized")
                continue

            # Get GPIO and direction
            if (
                self.esc_gpio_comboboxes[index] is None
                or self.esc_direction_comboboxes[index] is None
            ):
                print(f"Error: ESC {esc_id} comboboxes not initialized")
                continue

            gpio_combobox: ttk.Combobox = cast(
                ttk.Combobox, self.esc_gpio_comboboxes[index]
            )
            direction_combobox: ttk.Combobox = cast(
                ttk.Combobox, self.esc_direction_comboboxes[index]
            )
            gpio_str: str = gpio_combobox.get()
            direction_str: str = direction_combobox.get()

            # Map GPIO to number (GPIO9 -> 9)
            gpio_num = int(gpio_str.replace("GPIO", ""))

            # Map direction to number (Normal -> 0, Inverted -> 1)
            direction_num = 0 if direction_str == "Normal" else 1

            # Get calibration values
            if hasattr(self, "esc_calibration_entries") and index < len(
                self.esc_calibration_entries
            ):
                calib_entries = self.esc_calibration_entries[index]
                try:
                    calib_values = [int(entry.get()) for entry in calib_entries]
                except ValueError:
                    print(f"Error: Invalid calibration values for ESC {esc_id}")
                    continue
            else:
                calib_values = self.DEFAULT_ESC_CONFIG[index]["calibration"]

            # Send init command: esc <id> init <gpio_num>
            init_command = f"esc {esc_id} init {gpio_num}"
            self.parent.master.after(
                command_delay,
                lambda cmd=init_command, idx=index: self._send_init_command(cmd, idx),
            )
            command_delay += 200

            # Send direction command: esc <id> dir <direction_num>
            dir_command = f"esc {esc_id} dir {direction_num}"
            self.parent.master.after(
                command_delay, lambda cmd=dir_command: self._send_command_to_serial(cmd)
            )
            command_delay += 200

            # Send calibration command: esc [1-4] cali [bw_max] [bw_min] [idle] [fw_min] [fw_max]
            cali_command = f"esc {esc_id} cali {calib_values[0]} {calib_values[1]} {calib_values[2]} {calib_values[3]} {calib_values[4]}"
            self.parent.master.after(
                command_delay,
                lambda cmd=cali_command: self._send_command_to_serial(cmd),
            )
            command_delay += 200

            # Send power test sequence: 0.00, -0.01, 0.00, 0.01, 0.00
            power_sequence = [0.00, -0.01, 0.00, 0.01, 0.00]
            for power_val in power_sequence:
                pw_command = f"esc {esc_id} pw {power_val:.2f}"
                self.parent.master.after(
                    command_delay,
                    lambda cmd=pw_command: self._send_command_to_serial(cmd),
                )
                command_delay += 750

    def _send_init_command(self, command: str, index: int) -> None:
        """Send init command and mark ESC as initialized."""
        self._send_command_to_serial(command)
        self.esc_initialized[index] = True
        # Reset power slider to 0.00 before disabling it
        if index < len(self.esc_power_sliders):
            self.esc_power_sliders[index].set(0)
        self.update_esc_config_state(index)
        # Update button states after init
        self.update_esc_controls_state()

    def deinit_escs(self) -> None:
        """Send deinit commands for enabled ESCs that have been initialized."""
        command_delay = 0

        for index in range(4):
            esc_id = index + 1
            # Skip deselected ESCs
            if not self.esc_selected[index].get():
                print(f"ESC {esc_id} is not selected, skipping deinit")
                continue

            # Skip ESCs that haven't been initialized
            if not self.esc_initialized[index]:
                print(f"ESC {esc_id} is not initialized, skipping deinit")
                continue

            deinit_command = f"esc {esc_id} deinit"
            self.parent.master.after(
                command_delay,
                lambda cmd=deinit_command, idx=index: self._send_deinit_command(
                    cmd, idx
                ),
            )
            command_delay += 200

    def _send_deinit_command(self, command: str, index: int) -> None:
        """Send deinit command and mark ESC as deinitialized."""
        self._send_command_to_serial(command)
        self.esc_initialized[index] = False
        # Reset power slider to 0.00 before unlocking it
        if index < len(self.esc_power_sliders):
            self.esc_power_sliders[index].set(0)
        self.update_esc_config_state(index)
        # Update button states after deinit
        self.update_esc_controls_state()

    def update_esc_config_state(self, index: int) -> None:
        """Update UI state for a specific ESC based on initialization status."""
        is_initialized = self.esc_initialized[index]

        # Lock/unlock GPIO combobox
        if self.esc_gpio_comboboxes[index] is not None:
            gpio_box: ttk.Combobox = cast(ttk.Combobox, self.esc_gpio_comboboxes[index])
            gpio_box.config(state="disabled" if is_initialized else "readonly")

        # Lock/unlock Direction combobox
        if self.esc_direction_comboboxes[index] is not None:
            direction_box: ttk.Combobox = cast(
                ttk.Combobox, self.esc_direction_comboboxes[index]
            )
            direction_box.config(state="disabled" if is_initialized else "readonly")

        # Lock/unlock Calibration entries
        if hasattr(self, "esc_calibration_entries") and index < len(
            self.esc_calibration_entries
        ):
            for entry in self.esc_calibration_entries[index]:
                entry.config(state="disabled" if is_initialized else "normal")

        # Enable/disable Power slider
        if hasattr(self, "esc_power_sliders") and index < len(self.esc_power_sliders):
            self.esc_power_sliders[index].config(
                state="normal" if is_initialized else "disabled"
            )

        # Lock frequency if any ESC is initialized
        any_initialized = any(self.esc_initialized)
        self.frequency_combobox.config(
            state="disabled" if any_initialized else "readonly"
        )

    def _reset_power_slider(self, index: int) -> None:
        """Reset power slider to zero on right-click."""
        if hasattr(self, "esc_power_sliders") and index < len(self.esc_power_sliders):
            self.esc_power_sliders[index].set(0)

    def update_esc_controls_state(self) -> None:
        """Update ESC control button state based on serial connection and ESC states."""
        is_connected = self.parent.serial.is_connected()

        # Determine which ESCs are selected
        selected_indices = [i for i in range(4) if self.esc_selected[i].get()]

        if not is_connected:
            # Disable both buttons if not connected
            self.init_escs_button.config(state="disabled")
            self.deinit_escs_button.config(state="disabled")
        else:
            # Check if there are any selected ESCs that haven't been initialized
            has_uninitialized_selected = any(
                not self.esc_initialized[i] for i in selected_indices
            )
            # Check if there are any selected ESCs that have been initialized
            has_initialized_selected = any(
                self.esc_initialized[i] for i in selected_indices
            )

            # Enable Init button if there are selected ESCs that haven't been initialized
            self.init_escs_button.config(
                state="normal" if has_uninitialized_selected else "disabled"
            )
            # Enable Deinit button if there are selected ESCs that have been initialized
            self.deinit_escs_button.config(
                state="normal" if has_initialized_selected else "disabled"
            )

    def _on_power_slider_changed(self, index: int, slider_value: int) -> None:
        """Handle power slider change with throttling - only send newest value at timed intervals."""
        # Convert slider value (-100 to 100) to power value (-1.00 to 1.00)
        power: float = slider_value / 100.0

        # Update the value display label immediately with color coding
        if hasattr(self, "esc_power_value_labels") and index < len(
            self.esc_power_value_labels
        ):
            label: tk.Label = self.esc_power_value_labels[index]
            label.config(text=f"{power:.2f}")

            # Update color based on power value
            if power == 0.0:
                label.config(bg="#90EE90")  # Green for 0.00
            elif power > 0.0:
                label.config(bg="#FFFF00")  # Yellow for > 0.00
            else:  # power < 0.0
                label.config(bg="#FFA500")  # Orange for < 0.00

        # Store the pending power value (only latest value is kept)
        self.esc_power_pending[index] = power

        # If no send is already scheduled, schedule one after 75ms
        if not self.esc_power_send_scheduled[index]:
            self.esc_power_send_scheduled[index] = True
            self.parent.master.after(
                75, lambda idx=index: self._send_pending_power(idx)
            )

    def _send_pending_power(self, index: int) -> None:
        """Send the latest pending power value for an ESC."""
        if self.esc_power_pending[index] is not None:
            power = self.esc_power_pending[index]
            esc_id = index + 1
            command = f"esc {esc_id} pw {power:.2f}"
            threading.Thread(
                target=self._send_command_to_serial, args=(command,), daemon=True
            ).start()
            self.esc_power_pending[index] = None

        # Mark that send is no longer scheduled
        self.esc_power_send_scheduled[index] = False

    def _send_command_to_serial(self, command: str) -> None:
        """Helper function to send a command to serial via parent SerialPlotterApp."""
        try:
            if not command.endswith("\n"):
                command += "\n"

            if self.parent.serial.is_connected():
                self.parent.serial.send(command)
                # Log the command
                threading.Thread(
                    target=self.parent._async_log_and_display,
                    args=(command, True),
                    daemon=True,
                ).start()
            else:
                print("Serial port is not connected")
        except Exception as e:
            print(f"Error sending command: {e}")

    def _create_esc_section(self, parent: tk.Frame, index: int, esc_id: int) -> None:
        """Create a section for one ESC configuration."""
        section_frame: tk.LabelFrame = tk.LabelFrame(
            master=parent,
            text=f"ESC {esc_id}",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10,
        )
        section_frame.pack(fill=tk.X, pady=5)

        # GPIO and Direction on same line with Enable toggle on right
        config_frame: tk.Frame = tk.Frame(master=section_frame)
        config_frame.pack(fill=tk.X, pady=5)

        # GPIO frame (left)
        gpio_frame: tk.Frame = tk.Frame(master=config_frame)
        gpio_frame.pack(side=tk.LEFT, padx=5)

        gpio_label: tk.Label = tk.Label(master=gpio_frame, text="GPIO:", anchor="w")
        gpio_label.pack(side=tk.LEFT, padx=2)

        gpio_combobox: ttk.Combobox = ttk.Combobox(
            master=gpio_frame,
            values=self.GPIO_OPTIONS,
            state="readonly",
            width=12,
        )
        gpio_combobox.set(self.DEFAULT_ESC_CONFIG[index]["gpio"])
        gpio_combobox.pack(side=tk.LEFT, padx=2)

        # Direction frame (left-center)
        direction_frame: tk.Frame = tk.Frame(master=config_frame)
        direction_frame.pack(side=tk.LEFT, padx=5)

        direction_label: tk.Label = tk.Label(
            master=direction_frame, text="Direction:", anchor="w"
        )
        direction_label.pack(side=tk.LEFT, padx=2)

        direction_combobox: ttk.Combobox = ttk.Combobox(
            master=direction_frame,
            values=self.DIRECTION_OPTIONS,
            state="readonly",
            width=12,
        )
        direction_combobox.set(self.DEFAULT_ESC_CONFIG[index]["direction"])
        direction_combobox.pack(side=tk.LEFT, padx=2)

        # Selected toggle on right side
        toggle_checkbox: tk.Checkbutton = tk.Checkbutton(
            master=config_frame,
            text="Selected",
            variable=self.esc_selected[index],
            anchor="w",
            command=self.update_esc_controls_state,
        )
        toggle_checkbox.pack(side=tk.RIGHT, padx=5)

        self.esc_gpio_comboboxes[index] = gpio_combobox
        self.esc_direction_comboboxes[index] = direction_combobox

        # Calibration section with label on left and values on right
        calib_frame: tk.Frame = tk.Frame(master=section_frame)
        calib_frame.pack(fill=tk.X, pady=(10, 5))

        calib_label: tk.Label = tk.Label(
            master=calib_frame, text="Calibrations:", anchor="w"
        )
        calib_label.pack(side=tk.LEFT, padx=5)

        calib_values_frame: tk.Frame = tk.Frame(master=calib_frame)
        calib_values_frame.pack(side=tk.RIGHT, padx=5)

        calib_entries: list[tk.Entry] = []
        calib_labels: list[str] = ["BW Max", "BW Min", "Idle", "FW Min", "FW Max"]
        default_calib: list[int] = self.DEFAULT_ESC_CONFIG[index]["calibration"]  # type: ignore

        for i, calib_label_text in enumerate(calib_labels):
            label = tk.Label(
                master=calib_values_frame,
                text=f"{calib_label_text}:",
                width=8,
                anchor="e",
            )
            label.pack(side=tk.LEFT, padx=2)

            entry = tk.Entry(master=calib_values_frame, width=6)
            entry.insert(0, str(default_calib[i]))
            entry.pack(side=tk.LEFT, padx=1)
            calib_entries.append(entry)

        # Store calibration entries for this ESC
        self.esc_calibration_entries.append(calib_entries)

        # Motor power slider (-1.00 to 1.00)
        power_frame: tk.Frame = tk.Frame(master=section_frame)
        power_frame.pack(fill=tk.X, pady=(10, 5))

        power_label: tk.Label = tk.Label(
            master=power_frame, text="Motor Power:", anchor="w"
        )
        power_label.pack(side=tk.LEFT, padx=5)

        # Create a frame for slider and value display
        slider_container: tk.Frame = tk.Frame(master=power_frame)
        slider_container.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        # Power slider with range -100 to 100 (will be converted to -1.00 to 1.00)
        power_slider: tk.Scale = tk.Scale(
            master=slider_container,
            from_=-100,
            to=100,
            orient=tk.HORIZONTAL,
            command=lambda val: self._on_power_slider_changed(index, int(val)),
            state="disabled",  # Start disabled, enabled only when ESC is initialized
        )
        power_slider.set(0)
        power_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # Bind right-click to reset slider to zero (bind to parent frame to work with disabled state)
        slider_container.bind(
            "<Button-3>", lambda event, idx=index: self._reset_power_slider(idx)
        )

        # Power value display label with color coding and click-to-reset
        power_value_label: tk.Label = tk.Label(
            master=slider_container,
            text="0.00",
            width=6,
            anchor="center",
            bg="#90EE90",  # Green for 0.00
            fg="black",
            relief=tk.SUNKEN,
            bd=2,
        )
        power_value_label.pack(side=tk.LEFT, padx=5)

        # Bind all mouse clicks to reset slider to zero
        power_value_label.bind(
            "<Button-1>", lambda event, idx=index: self._reset_power_slider(idx)
        )  # Left click
        power_value_label.bind(
            "<Button-2>", lambda event, idx=index: self._reset_power_slider(idx)
        )  # Middle click
        power_value_label.bind(
            "<Button-3>", lambda event, idx=index: self._reset_power_slider(idx)
        )  # Right click

        # Store power slider and value label for this ESC
        self.esc_power_sliders.append(power_slider)
        self.esc_power_value_labels.append(power_value_label)


class LightControlApp:
    """Light control window for managing a single LED light."""

    # GPIO options from GPIO0-GPIO21 and GPIO26-GPIO48
    GPIO_OPTIONS: list[str] = [f"GPIO{i}" for i in range(22)] + [f"GPIO{i}" for i in range(26, 49)]
    FREQUENCY_OPTIONS: list[str] = ["50Hz", "60Hz", "100Hz", "120Hz", "440Hz", "1000Hz", "10000Hz", "44100Hz", "48000Hz", "96000Hz"]
    GAMMA: float = 2.3  # Gamma correction value (2.3 for non-linear brightness)

    def __init__(self, parent: SerialPlotterApp) -> None:
        self.parent: SerialPlotterApp = parent
        self.window: tk.Toplevel = tk.Toplevel(parent.master)
        self.window.title("Light Control")
        self.window.geometry("600x170")
        
        # Handle window close to hide instead of destroy
        self.window.protocol("WM_DELETE_WINDOW", self.on_window_close)
        
        # Initialize state
        self.light_initialized: bool = False
        self.light_power_pending: float | None = None
        self.light_power_send_scheduled: bool = False
        
        # Create main frame
        main_frame: tk.Frame = tk.Frame(master=self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # LED Light section
        light_frame: tk.LabelFrame = tk.LabelFrame(
            master=main_frame,
            text="LED Light",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10,
        )
        light_frame.pack(fill=tk.X, pady=5)
        
        # GPIO and Frequency on same line
        config_frame: tk.Frame = tk.Frame(master=light_frame)
        config_frame.pack(fill=tk.X, pady=5)
        
        # GPIO frame (left)
        gpio_frame: tk.Frame = tk.Frame(master=config_frame)
        gpio_frame.pack(side=tk.LEFT, padx=5)
        
        gpio_label: tk.Label = tk.Label(master=gpio_frame, text="GPIO:", anchor="w")
        gpio_label.pack(side=tk.LEFT, padx=2)
        
        self.gpio_combobox: ttk.Combobox = ttk.Combobox(
            master=gpio_frame,
            values=self.GPIO_OPTIONS,
            state="readonly",
            width=12,
        )
        self.gpio_combobox.set("GPIO14")
        self.gpio_combobox.pack(side=tk.LEFT, padx=2)
        
        # Frequency frame (center)
        freq_frame: tk.Frame = tk.Frame(master=config_frame)
        freq_frame.pack(side=tk.LEFT, padx=5)
        
        freq_label: tk.Label = tk.Label(master=freq_frame, text="Frequency:", anchor="w")
        freq_label.pack(side=tk.LEFT, padx=2)
        
        self.frequency_combobox: ttk.Combobox = ttk.Combobox(
            master=freq_frame,
            values=self.FREQUENCY_OPTIONS,
            state="readonly",
            width=12,
        )
        self.frequency_combobox.set("44100Hz")
        self.frequency_combobox.pack(side=tk.LEFT, padx=2)
        
        # Init and Deinit buttons on right
        button_frame: tk.Frame = tk.Frame(master=config_frame)
        button_frame.pack(side=tk.RIGHT, padx=5)
        
        self.init_button: tk.Button = tk.Button(
            master=button_frame,
            text="Init",
            command=self.init_light,
            width=10,
        )
        self.init_button.pack(side=tk.LEFT, padx=2)
        
        self.deinit_button: tk.Button = tk.Button(
            master=button_frame,
            text="Deinit",
            command=self.deinit_light,
            width=10,
        )
        self.deinit_button.pack(side=tk.LEFT, padx=2)
        
        # Power level slider (0-7 mapped to 0-256 with gamma 2.2)
        power_frame: tk.Frame = tk.Frame(master=light_frame)
        power_frame.pack(fill=tk.X, pady=(10, 5))
        
        power_label: tk.Label = tk.Label(master=power_frame, text="Power Level:", anchor="w")
        power_label.pack(side=tk.LEFT, padx=5)
        
        # Create a frame for slider and value display
        slider_container: tk.Frame = tk.Frame(master=power_frame)
        slider_container.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        # Power slider with range 0 to 7
        self.power_slider: tk.Scale = tk.Scale(
            master=slider_container,
            from_=0,
            to=7,
            orient=tk.HORIZONTAL,
            command=lambda val: self._on_power_slider_changed(int(val)),
            state="disabled",  # Start disabled, enabled only when light is initialized
        )
        self.power_slider.set(0)
        self.power_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        # Bind right-click to reset slider to zero
        slider_container.bind("<Button-3>", lambda event: self._reset_power_slider())
        
        # Power value display label
        self.power_value_label: tk.Label = tk.Label(
            master=slider_container,
            text="0/256",
            width=8,
            anchor="center",
            bg="#90EE90",
            fg="black",
            relief=tk.SUNKEN,
            bd=2,
        )
        self.power_value_label.pack(side=tk.LEFT, padx=5)
        
        # Bind all mouse clicks to reset slider to zero
        self.power_value_label.bind("<Button-1>", lambda event: self._reset_power_slider())
        self.power_value_label.bind("<Button-2>", lambda event: self._reset_power_slider())
        self.power_value_label.bind("<Button-3>", lambda event: self._reset_power_slider())
        
        # Update button states
        self.update_light_controls_state()

    def _level_to_pwm(self, level: int) -> int:
        """Convert power level (0-7) to PWM value (0-256) using gamma correction."""
        normalized = level / 7.0  # Normalize to 0-1
        gamma_corrected = pow(normalized, self.GAMMA)  # Apply gamma correction (gamma = 1/2.2)
        pwm_value = int(gamma_corrected * 256)
        return min(pwm_value, 256)  # Ensure we don't exceed 256

    def _on_power_slider_changed(self, level: int) -> None:
        """Handle power slider change with throttling."""
        pwm_value = self._level_to_pwm(level)
        
        # Update the value display label
        self.power_value_label.config(text=f"{pwm_value}/256")
        
        # Store the pending power value
        self.light_power_pending = pwm_value
        
        # If no send is already scheduled, schedule one after 75ms
        if not self.light_power_send_scheduled:
            self.light_power_send_scheduled = True
            self.parent.master.after(75, self._send_pending_power)

    def _send_pending_power(self) -> None:
        """Send the latest pending power value for the light."""
        if self.light_power_pending is not None and self.gpio_combobox is not None:
            pwm_value = self.light_power_pending
            gpio_str: str = self.gpio_combobox.get()
            gpio_num = int(gpio_str.replace("GPIO", ""))
            command = f"ledc {gpio_num} set {pwm_value}"
            threading.Thread(
                target=self._send_command_to_serial,
                args=(command,),
                daemon=True
            ).start()
            self.light_power_pending = None
        
        # Mark that send is no longer scheduled
        self.light_power_send_scheduled = False

    def _reset_power_slider(self) -> None:
        """Reset power slider to zero on right-click."""
        self.power_slider.set(0)

    def _send_command_to_serial(self, command: str) -> None:
        """Helper function to send a command to serial via parent SerialPlotterApp."""
        try:
            if not command.endswith("\n"):
                command += "\n"
            
            if self.parent.serial.is_connected():
                self.parent.serial.send(command)
                # Log the command
                threading.Thread(
                    target=self.parent._async_log_and_display,
                    args=(command, True),
                    daemon=True
                ).start()
            else:
                print("Serial port is not connected")
        except Exception as e:
            print(f"Error sending command: {e}")

    def init_light(self) -> None:
        """Send init command for the light with GPIO and frequency."""
        if self.gpio_combobox is None:
            print("Error: GPIO combobox is not initialized")
            return
        
        gpio_str: str = self.gpio_combobox.get()
        gpio_num = int(gpio_str.replace("GPIO", ""))
        
        freq_str: str = self.frequency_combobox.get()
        # Extract frequency number from string (e.g., "44100Hz" -> "44100")
        freq_num = freq_str.replace("Hz", "")
        
        # Send config command first: ledc config [Hz]
        config_command = f"ledc config {freq_num}"
        self.parent.master.after(0, lambda cmd=config_command: self._send_command_to_serial(cmd))
        
        # Send init command: ledc [gpio] init 0
        init_command = f"ledc {gpio_num} init 0"
        self.parent.master.after(200, lambda cmd=init_command: self._send_command_to_serial(cmd))
        
        self.light_initialized = True
        self.parent.master.after(400, self.update_light_config_state)
        self.parent.master.after(400, self.update_light_controls_state)

    def deinit_light(self) -> None:
        """Send deinit command for the light."""
        if self.gpio_combobox is None:
            print("Error: GPIO combobox is not initialized")
            return
        
        gpio_str: str = self.gpio_combobox.get()
        gpio_num = int(gpio_str.replace("GPIO", ""))
        
        # Send set 0 command first: ledc [gpio] set 0
        set_zero_command = f"ledc {gpio_num} set 0"
        self.parent.master.after(0, lambda cmd=set_zero_command: self._send_command_to_serial(cmd))
        
        # Send deinit command: ledc [gpio] deinit
        deinit_command = f"ledc {gpio_num} deinit"
        self.parent.master.after(200, lambda cmd=deinit_command: self._send_command_to_serial(cmd))
        
        # Send delete command: ledc delete
        delete_command = "ledc delete"
        self.parent.master.after(400, lambda cmd=delete_command: self._send_command_to_serial(cmd))
        
        self.light_initialized = False
        # Reset power slider to 0.00 before unlocking it
        self.power_slider.set(0)
        self.parent.master.after(600, self.update_light_config_state)
        self.parent.master.after(600, self.update_light_controls_state)

    def update_light_config_state(self) -> None:
        """Update UI state based on initialization status."""
        # Lock/unlock GPIO combobox
        self.gpio_combobox.config(state="disabled" if self.light_initialized else "readonly")
        
        # Lock/unlock Frequency combobox
        self.frequency_combobox.config(state="disabled" if self.light_initialized else "readonly")
        
        # Enable/disable Power slider
        self.power_slider.config(state="normal" if self.light_initialized else "disabled")

    def update_light_controls_state(self) -> None:
        """Update button state based on serial connection and initialization."""
        is_connected = self.parent.serial.is_connected()
        
        if not is_connected:
            self.init_button.config(state="disabled")
            self.deinit_button.config(state="disabled")
        else:
            # Enable Init button if not initialized
            self.init_button.config(state="normal" if not self.light_initialized else "disabled")
            # Enable Deinit button if initialized
            self.deinit_button.config(state="normal" if self.light_initialized else "disabled")

    def on_window_close(self) -> None:
        """Hide window instead of closing it."""
        self.window.withdraw()


def on_closing():
    print("Exiting")
    serial_app.close()
    root.quit()  # This will exit the main loop
    root.destroy()


if __name__ == "__main__":

    root = tk.Tk()
    root.title("IMU Plotter")
    root.geometry("1000x720")

    serial_app = SerialPlotterApp(master=root)
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
