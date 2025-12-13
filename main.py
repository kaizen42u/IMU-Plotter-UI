import re
import threading
import tkinter as tk
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
        
        self._reconnect_enabled: bool = False  # Only enabled after manual connect, disabled on manual disconnect
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
        self.port_selection_label = tk.Label(master=self.control_frame, text="COM Port:")
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
        common_baudrates = ["9600", "14400", "19200", "38400", "57600", "115200", "230400", "460800", "921600"]
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
            master=self.graphs_frame, title="Linear Acceleration (G)", max_samples=GRAPH_MAX_SAMPLES
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
        self.imu_data_toggle_button.grid(row=0, column=0)

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
            self.terminal_show_message(f"{ANSI.bGreen}Logging started: {self.log_file_path}{ANSI.default}")
        except Exception as e:
            self.terminal_show_message(f"{ANSI.bRed}Failed to start logging: {e}{ANSI.default}")
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
            self.terminal_show_message(f"{ANSI.bRed}Failed to stop logging: {e}{ANSI.default}")

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
            log_line = f"({timestamp}:{ms:03d})({direction}) | {clean_data}\n"
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
        self.write_log(line, " R")
        self.update_graphs(line)
        self.update_terminal(line)

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
                print(f"Auto-reconnect failed (attempt {self._reconnect_attempts}): {e}")
                if self._reconnect_attempts < 5:
                    self.master.after(100, self.attempt_reconnect)
                else:
                    print(f"Auto-reconnect failed after 5 attempts. Manual reconnection required.")
                    self._reconnect_attempts = 0

    def serial_connect_toggle_button_update(self) -> None:
        display_text = "Disconnect" if self.serial.is_connected() else "Connect"
        self.serial_connect_toggle_button.configure(text=display_text)
        
        # Disable/enable COM port and baudrate selection based on connection state
        is_connected = self.serial.is_connected()
        self.port_selection_combobox.configure(state="disabled" if is_connected else "readonly")
        self.baudrate_combobox.configure(state="disabled" if is_connected else "normal")

    def serial_connect_toggle(self) -> None:
        # If already connected, disconnect
        if self.serial.is_connected():
            self.serial.disconnect()
            self._reconnect_enabled = False  # Disable auto-reconnect on manual disconnect
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
            self._reconnect_enabled = True  # Enable auto-reconnect on successful manual connect
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

    def update_terminal(self, reading: str) -> None:
        is_imu_data: bool = bool(
            re.search(SERIAL_IMU_BNO085_DATA_REGEX, reading)
        )
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
            self.terminal_show_message(f"{ANSI.bRed}Error: Serial port is not connected{ANSI.default}")
            return
        
        # Append newline if not already present
        if not command.endswith("\n"):
            command += "\n"
        
        success = self.serial.send(command)
        if success:
            self.write_log(command, "T ")
            self.terminal_show_message(f"{ANSI.bGreen}> {command.rstrip()}{ANSI.default}")
        else:
            self.terminal_show_message(f"{ANSI.bRed}Error: Failed to send command{ANSI.default}")
        
        # Keep textfield populated but select all text for quick resend
        self.send_command_entry.select_range(0, tk.END)
        self.send_command_entry.focus()

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
