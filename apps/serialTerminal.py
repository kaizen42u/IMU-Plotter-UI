import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from typing import List, Callable
from queue import Queue

from configManager import get_config_manager
from serialHandler import serialHandler
from ansiEncoding import ANSI
from tkAutocompleteCombobox import tkAutocompleteCombobox
from tkTerminal import tkTerminal

# Load terminal settings from config
config = get_config_manager()


class SerialTerminal:
    """Handles serial communication and terminal display."""

    def __init__(self, master: tk.Tk | tk.Frame) -> None:
        self.master: tk.Tk | tk.Frame = master
        self._reconnect_enabled: bool = False
        self._reconnect_attempts: int = 0

        # Get config manager
        config = get_config_manager()

        # Load serial settings from config
        self.port: str = config.get("serial.port", "/dev/ttyUSB0")
        self.baudrate: int = config.get("serial.baudrate", 115200)
        self.auto_scroll_enabled: bool = config.get("serial.auto_scroll", True)
        self.logging_enabled_default: bool = config.get("serial.logging_enabled", True)

        # Logging variables
        self.logging_enabled: bool = False
        self.log_file_path: Path | None = None
        self.log_file_handle = None
        self.log_queue: Queue = Queue()
        self.log_writer_thread: threading.Thread | None = None

        # Event filtering variables
        self.show_events: bool = True
        self.event_lines: List[str] = []  # Track event lines for toggling

        # Callbacks
        self._connection_state_callbacks: List[Callable[[], None]] = []
        self._line_received_callbacks: List[Callable[[str], None]] = []
        self._event_callbacks: dict[str, List[Callable[[str, str], None]]] = (
            {}
        )  # Maps event_id to list of callbacks (timestamp, data)
        self._pending_event_enables: set[str] = (
            set()
        )  # Track events waiting to be enabled

        # Command history
        self.command_history: List[str] = []
        self.history_index: int = -1

        self.serial: serialHandler = serialHandler()

        self.setup_ui()

        # Enable logging based on config
        self.logging_var.set(self.logging_enabled_default)
        if self.logging_enabled_default:
            self.start_logging()

        # Get a list of all available serial ports
        ports = self.serial.get_ports()
        self.port_selection_combobox.set_completion_list(ports)
        self.update_connect_button()

        self.serial.set_line_received_callback(self.serial_line_received)
        self.serial.set_log_callback(self.serial_log)
        self.serial.set_ports_changed_callback(self.serial_ports_changed)
        self.serial.set_disconnect_callback(self.serial_disconnected)

    def register_line_received_callback(self, callback: Callable[[str], None]) -> None:
        """Register a callback to be called when a line is received from serial."""
        self._line_received_callbacks.append(callback)

    def register_event_callback(
        self, event_id: str, callback: Callable[[str, str], None]
    ) -> None:
        """Register a callback for a specific event ID.

        The callback will be called with (timestamp, data) from the event line.
        Event line format: "[EVENT <event_id>] [<timestamp> ms] <data>"
        Also automatically enables the event on the device.
        """
        if event_id not in self._event_callbacks:
            self._event_callbacks[event_id] = []
            # Enable the event on the device when first callback is registered
            self._enable_event(event_id)

        self._event_callbacks[event_id].append(callback)

    def _enable_event(self, event_id: str) -> None:
        """Enable an event on the device."""
        try:

            hex_id = event_id

            if self.serial.is_connected():
                enable_command = f"event enable {hex_id}"
                self.send_command(enable_command + "\n")
            else:
                self._pending_event_enables.add(hex_id)
        except Exception as e:
            print(f"[ERROR] Error enabling event {event_id}: {e}")

    def _send_pending_events(self) -> None:
        """Send all pending event enable commands after connection is established."""
        if not self._pending_event_enables:
            return

        for hex_id in self._pending_event_enables:
            try:
                enable_command = f"event enable {hex_id}"
                self.send_command(enable_command + "\n")
            except Exception as e:
                print(f"[ERROR] Error sending pending event enable {hex_id}: {e}")

        self._pending_event_enables.clear()

    def setup_ui(self) -> None:
        # Use the entire master frame for serial terminal UI
        self.control_frame = tk.Frame(master=self.master)
        self.control_frame.grid(row=0, column=0, sticky="ew")

        # Create a label for COM port selection
        self.port_selection_label = tk.Label(
            master=self.control_frame, text="COM Port:"
        )
        self.port_selection_label.grid(row=0, column=0, padx=5)

        # Create a dropdown menu for available ports
        self.port_selection_combobox = tkAutocompleteCombobox(
            master=self.control_frame, state="readonly"
        )
        self.port_selection_combobox.set(self.port)
        self.port_selection_combobox.grid(row=0, column=1, padx=(5, 15))

        # Create a label for baudrate selection
        self.baudrate_label = tk.Label(master=self.control_frame, text="Baudrate:")
        self.baudrate_label.grid(row=0, column=2, padx=5)

        # Create a dropdown menu for baudrate selection
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
        self.baudrate_combobox.set(str(self.baudrate))
        self.baudrate_combobox.grid(row=0, column=3, padx=(5, 15))

        # Create serial connect/disconnect button
        self.serial_connect_toggle_button = tk.Button(
            master=self.control_frame, text="Connect", command=self.toggle_connection
        )
        self.serial_connect_toggle_button.config(width=20)
        self.serial_connect_toggle_button.grid(row=0, column=4, padx=5)

        # Create terminal auto scroll checkbox
        self.terminal_auto_scroll_var = tk.BooleanVar(
            master=self.master, value=self.auto_scroll_enabled
        )
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
        self.logging_var = tk.BooleanVar(
            master=self.master, value=self.logging_enabled_default
        )
        self.logging_checkbox = tk.Checkbutton(
            master=self.control_frame,
            text="Logging",
            variable=self.logging_var,
            command=self.toggle_logging,
        )
        self.logging_checkbox.config(width=20)
        self.logging_checkbox.grid(row=0, column=6, padx=5)

        # Configure grid to allow terminal to expand and compress other rows
        self.master.grid_rowconfigure(0, weight=0)  # Top controls: minimal height
        self.master.grid_rowconfigure(1, weight=1)  # Terminal: expandable
        self.master.grid_rowconfigure(2, weight=0)  # Send command: minimal height
        self.master.grid_columnconfigure(0, weight=1)

        # Create the serial terminal
        self.terminal = tkTerminal(
            master=self.master, lines=config.get("serial.terminal_max_width", 180)
        )
        self.terminal.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)

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
        # Bind up/down arrow keys for command history
        self.send_command_entry.bind("<Up>", lambda event: self._history_previous())
        self.send_command_entry.bind("<Down>", lambda event: self._history_next())

        # Create a send button
        self.send_command_button = tk.Button(
            master=self.send_command_frame, text="Send", command=self.send_command
        )
        self.send_command_button.grid(row=0, column=2, padx=5)

        # Create a show/hide events button
        self.toggle_events_button = tk.Button(
            master=self.send_command_frame,
            text="Hide Events",
            command=self.toggle_events,
        )
        self.toggle_events_button.grid(row=0, column=3, padx=5)

    def register_connection_state_callback(self, callback: Callable[[], None]) -> None:
        """Register a callback to be called when connection state changes."""
        self._connection_state_callbacks.append(callback)

    def _notify_connection_state_changed(self) -> None:
        """Notify all registered callbacks of connection state change."""
        # If we just connected, send any pending event enables
        if self.serial.is_connected() and self._pending_event_enables:
            print(f"[DEBUG] Connection established, sending pending events")
            self._send_pending_events()

        for callback in self._connection_state_callbacks:
            try:
                callback()
            except Exception as e:
                print(f"Error in connection state callback: {e}")

    def toggle_logging(self) -> None:
        if self.logging_var.get():
            self.start_logging()
        else:
            self.stop_logging()

    def start_logging(self) -> None:
        try:
            session_logs_dir = Path("./session_logs")
            session_logs_dir.mkdir(exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file_path = session_logs_dir / f"{timestamp}.log"

            self.log_file_handle = open(self.log_file_path, "w")
            self.logging_enabled = True

            # Start the dedicated writer thread
            self.log_writer_thread = threading.Thread(
                target=self._log_writer_thread, daemon=True
            )
            self.log_writer_thread.start()

            self.show_message(
                f"{ANSI.bGreen}Logging started: {self.log_file_path}{ANSI.default}"
            )
        except Exception as e:
            self.show_message(f"{ANSI.bRed}Failed to start logging: {e}{ANSI.default}")
            self.logging_var.set(False)

    def stop_logging(self) -> None:
        """Stop logging and close log file."""
        try:
            if self.logging_enabled:
                self.logging_enabled = False
                # Signal the writer thread to stop by putting None in queue
                self.log_queue.put(None)

                # Wait for writer thread to finish
                if self.log_writer_thread and self.log_writer_thread.is_alive():
                    self.log_writer_thread.join(timeout=2)

            if self.log_file_handle:
                self.log_file_handle.close()
                self.log_file_handle = None

            self.show_message(f"{ANSI.bGreen}Logging stopped{ANSI.default}")
        except Exception as e:
            self.show_message(f"{ANSI.bRed}Failed to stop logging: {e}{ANSI.default}")

    def write_log(self, direction: str, data: str) -> None:
        """Write data to session log. direction should be 'tx' or 'rx'."""
        if not self.logging_enabled:
            return

        try:
            now = datetime.now()
            timestamp = now.strftime("%y%m%d-%H%M%S")
            ms = now.microsecond // 1000

            clean_data = data.rstrip("\n\r")

            log_line = f"({timestamp}.{ms:03d})({direction}) | {clean_data}\n"
            # Put the log line in the queue for the writer thread to process
            self.log_queue.put(log_line)
        except Exception as e:
            print(f"[W] Error queueing log: {e}")

    def _log_writer_thread(self) -> None:
        """Dedicated thread for writing logs to file."""
        try:
            while self.logging_enabled:
                try:
                    # Block with timeout to allow graceful shutdown
                    log_line = self.log_queue.get(timeout=1)

                    # None is the sentinel value to stop the thread
                    if log_line is None:
                        break

                    if self.log_file_handle:
                        self.log_file_handle.write(log_line)
                        self.log_file_handle.flush()
                except:
                    # Timeout or other queue error, continue waiting
                    continue
        except Exception as e:
            print(f"[W] Error in log writer thread: {e}")

    def close(self) -> None:
        self._save_serial_config()
        if self.logging_enabled:
            self.stop_logging()
        self.serial.close()

    def _save_serial_config(self) -> None:
        """Save serial configuration to config file."""
        try:
            config = get_config_manager()
            config.set("serial.port", self.port_selection_combobox.get())
            config.set("serial.baudrate", int(self.baudrate_combobox.get()))
            config.set("serial.auto_scroll", self.terminal_auto_scroll_var.get())
            config.set("serial.logging_enabled", self.logging_var.get())
            config.save()
        except Exception as e:
            print(f"Error saving serial config: {e}")

    def serial_line_received(self, line: str) -> None:
        # Check if line is an event line
        is_event_line = line.strip().startswith("[EVENT")

        # Only display if not an event line, or if showing events
        if not is_event_line or self.show_events:
            # Schedule GUI updates on the main thread
            self.master.after(0, self.terminal.write, line + "\n")

        # Store event lines for later toggling
        if is_event_line:
            self.event_lines.append(line)
            # Parse event and call registered callbacks
            self._process_event_line(line)

        # Call all registered callbacks
        for callback in self._line_received_callbacks:
            try:
                self.master.after(0, callback, line)
            except Exception as e:
                print(f"Error in line received callback: {e}")

        # Log asynchronously to queue (writer thread handles it)
        if self.logging_enabled:
            self.write_log(" R", line)

    def serial_log(self, message: str) -> None:
        self.show_message(message)

    def serial_ports_changed(self, ports: List[str]) -> None:
        self.port_selection_combobox.set_completion_list(
            list(set(self.port_selection_combobox.get_completion_list() + ports))
        )
        self.update_connect_button()
        print(f"Ports changed: {ports}")

        selected_port = self.port_selection_combobox.get()
        if (
            self._reconnect_enabled
            and selected_port
            and selected_port in ports
            and not self.serial.is_connected()
        ):
            self.master.after(100, self.attempt_reconnect)

    def serial_disconnected(self, port: str) -> None:
        self.update_connect_button()
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
                self.update_connect_button()
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
                    print("Auto-reconnect failed after 5 attempts.")
                    self._reconnect_attempts = 0

    def update_connect_button(self) -> None:
        display_text = "Disconnect" if self.serial.is_connected() else "Connect"
        self.serial_connect_toggle_button.configure(text=display_text)

        is_connected = self.serial.is_connected()
        self.port_selection_combobox.configure(
            state="disabled" if is_connected else "readonly"
        )
        self.baudrate_combobox.configure(state="disabled" if is_connected else "normal")

        # Notify connection state change
        self._notify_connection_state_changed()

    def toggle_connection(self) -> None:
        if self.serial.is_connected():
            self.serial.disconnect()
            self._reconnect_enabled = False
            self.update_connect_button()
            print("Auto-reconnect disabled (manual disconnect)")
            return

        try:
            baudrate_str = self.baudrate_combobox.get()
            baudrate = int(baudrate_str) if baudrate_str else 115200

            self.serial.connect(self.port_selection_combobox.get(), baudrate=baudrate)
            self._reconnect_enabled = True
            self._reconnect_attempts = 0
            self.update_connect_button()
            print("Auto-reconnect enabled")
        except ValueError:
            self.show_message(f"Invalid baudrate: {self.baudrate_combobox.get()}")

    def send_command(self, command: str | None = None) -> bool:
        """Send a command over the serial port.

        Args:
            command: Command to send. If None, uses command from entry field.

        Returns:
            True if command was sent successfully, False otherwise.
        """
        # Track if called from UI
        from_ui = command is None

        # If no command provided, get from entry field
        if from_ui:
            command = self.send_command_entry.get()
            if not command:
                return False

        if not self.serial.is_connected():
            if from_ui:  # Only show UI message if called from UI
                self.show_message(
                    f"{ANSI.bRed}Error: Serial port is not connected{ANSI.default}"
                )
            return False

        if not command.endswith("\n"):
            command += "\n"

        # Add to history only if called from UI
        if from_ui:
            command_stripped = command.rstrip("\n")
            if command_stripped and (
                not self.command_history or self.command_history[-1] != command_stripped
            ):
                self.command_history.append(command_stripped)

            # Reset history index
            self.history_index = -1

        success = self.serial.send(command)

        if success:
            if self.logging_enabled:
                self.write_log("T ", command)
            self.master.after(
                0,
                lambda: self.show_message(
                    f"{ANSI.bGreen}> {command.rstrip()}{ANSI.default}"
                ),
            )

        # Update UI only if called from UI
        if from_ui:
            if success:
                # Keep the text in the entry and select it for easy re-sending
                self.send_command_entry.select_range(0, tk.END)
            else:
                self.show_message(
                    f"{ANSI.bRed}Error: Failed to send command{ANSI.default}"
                )

        return success

    def _history_previous(self) -> None:
        """Navigate to previous command in history."""
        if not self.command_history:
            return

        # Save current text if we're at the end of history
        if self.history_index == -1:
            self._history_current_text = self.send_command_entry.get()
            # Show the last command immediately on first Up press
            self.history_index = 0
        elif self.history_index < len(self.command_history) - 1:
            # Move to the next previous command
            self.history_index += 1
        else:
            # Already at the oldest command, don't go further
            return

        command = self.command_history[-(self.history_index + 1)]
        self.send_command_entry.delete(0, tk.END)
        self.send_command_entry.insert(0, command)
        # Move cursor to end of text
        self.send_command_entry.icursor(tk.END)

    def _history_next(self) -> None:
        """Navigate to next command in history."""
        if self.history_index <= 0:
            return

        self.history_index -= 1
        if self.history_index == -1:
            # Restore the text that was being edited
            text = getattr(self, "_history_current_text", "")
            self.send_command_entry.delete(0, tk.END)
            self.send_command_entry.insert(0, text)
        else:
            command = self.command_history[-(self.history_index + 1)]
            self.send_command_entry.delete(0, tk.END)
            self.send_command_entry.insert(0, command)

        # Move cursor to end of text
        self.send_command_entry.icursor(tk.END)

        self.send_command_entry.select_range(0, tk.END)
        self.send_command_entry.focus()

    def _process_event_line(self, line: str) -> None:
        """Parse an event line and call registered event callbacks.

        Event format: "[EVENT <event_id>] [<timestamp> ms] <data>"
        Example: "[EVENT 0x60] [       15765 ms]  8.24"
        Supports both decimal and hex event IDs (e.g., "60" or "0x60")
        """
        try:
            # Remove leading/trailing whitespace
            line = line.strip()

            # Check if line matches event format
            if not line.startswith("[EVENT "):
                return

            # Find the first closing bracket (end of event ID)
            bracket_end = line.find("]")
            if bracket_end == -1:
                return

            # Extract event ID
            event_id_part = line[
                7:bracket_end
            ].strip()  # Skip "[EVENT " and strip whitespace

            # Normalize event ID: strip "0x" prefix if present for hex values
            if event_id_part.lower().startswith("0x"):
                event_id_normalized = event_id_part[2:]  # Remove "0x" prefix
            else:
                event_id_normalized = event_id_part

            # Extract timestamp and data from the remaining part
            remaining = line[bracket_end + 1 :].strip()  # Everything after "]"

            timestamp = ""
            data = ""

            # Check if there's a timestamp bracket
            if remaining.startswith("["):
                ts_end = remaining.find("]")
                if ts_end != -1:
                    timestamp = remaining[
                        1:ts_end
                    ].strip()  # Extract timestamp content without brackets
                    data = remaining[
                        ts_end + 1 :
                    ].strip()  # Everything after timestamp bracket
            else:
                # Fallback: treat entire remaining as data (for backward compatibility)
                data = remaining

            # Call registered callbacks for this event ID (try both original and normalized)
            for event_id_key in [event_id_normalized, event_id_part]:
                if event_id_key in self._event_callbacks:
                    for callback in self._event_callbacks[event_id_key]:
                        try:
                            self.master.after(0, callback, timestamp, data)
                        except Exception as e:
                            print(f"Error in event callback for {event_id_key}: {e}")
        except Exception as e:
            print(f"Error processing event line: {e}")

    def toggle_events(self) -> None:
        """Toggle the display of event lines."""
        self.show_events = not self.show_events
        self.toggle_events_button.config(
            text="Hide Events" if self.show_events else "Show Events"
        )

        # Note: Toggling only affects new incoming lines.
        # To update existing displayed events, we would need to rebuild the terminal.
        self.show_message(
            f"{ANSI.bYellow}Events display: {'ON' if self.show_events else 'OFF'}{ANSI.default}"
        )

    def show_message(self, message: str) -> None:
        self.terminal.write(f"{ANSI.bBrightMagenta}{message}{ANSI.default}\n")
        print(message)
