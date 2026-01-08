"""Water Leakage Sensor application module."""

import tkinter as tk
from tkinter import ttk

from configManager import get_config_manager

# Load leakage configuration from config
config = get_config_manager()

# Event ID for leakage sensor status
EVENT_LEAKAGE_STATUS = "0x30"


class LeakageApp:
    """Application for water leakage sensor monitoring and control."""

    GPIO_OPTIONS: list[str] = [f"GPIO{i}" for i in range(22)] + [
        f"GPIO{i}" for i in range(26, 49)
    ]

    def __init__(self, parent) -> None:
        self.parent = parent
        self.window: tk.Toplevel = tk.Toplevel(parent.master)
        self.window.title("Leakage Sensor")
        self.window.geometry("600x450")

        self.window.protocol("WM_DELETE_WINDOW", self.on_window_close)

        # Load leakage config
        self.leakage_gpio = config.get("leakage.gpio", "GPIO2")
        self.leakage_calibration_scans = config.get("leakage.calibration_scans", 3)
        self.leakage_initialized: bool = False
        self.leakage_monitoring: bool = False

        # Register event callbacks with the serial terminal
        self.serial_terminal = parent
        self.serial_terminal.register_event_callback(
            EVENT_LEAKAGE_STATUS, self.on_leakage_status_event
        )

        # Register connection state callback
        self.serial_terminal.register_connection_state_callback(
            self.update_connection_state
        )

        # Current sensor values
        self.current_raw_value: str = "0"
        self.current_change_percent: str = "0.00%"
        self.current_state: str = "Unknown"
        self.current_health: str = "Unknown"

        main_frame: tk.Frame = tk.Frame(master=self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._create_config_section(main_frame)
        self._create_status_section(main_frame)
        self._create_control_section(main_frame)

        # Auto-size window to fit content
        self.window.update_idletasks()
        width = main_frame.winfo_reqwidth() + 20
        height = main_frame.winfo_reqheight() + 20
        self.window.geometry(f"{width}x{height}")

        self.update_connection_state()

    def _create_config_section(self, parent: tk.Frame) -> None:
        """Create the configuration section with GPIO selection."""
        config_frame: tk.LabelFrame = tk.LabelFrame(
            master=parent,
            text="Configuration",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10,
        )
        config_frame.pack(fill=tk.X, pady=5)

        # GPIO selection
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
        self.gpio_combobox.set(self.leakage_gpio)
        self.gpio_combobox.pack(side=tk.LEFT, padx=2)

        # Calibration scans
        calib_frame: tk.Frame = tk.Frame(master=config_frame)
        calib_frame.pack(side=tk.LEFT, padx=5)

        calib_label: tk.Label = tk.Label(
            master=calib_frame, text="Calib. Scans:", anchor="w"
        )
        calib_label.pack(side=tk.LEFT, padx=2)

        self.calib_scans_var = tk.StringVar(value=str(self.leakage_calibration_scans))
        self.calib_scans_entry: tk.Entry = tk.Entry(
            master=calib_frame,
            textvariable=self.calib_scans_var,
            width=5,
        )
        self.calib_scans_entry.pack(side=tk.LEFT, padx=2)
        self.calib_scans_entry.bind("<Return>", lambda e: self._save_leakage_config())

    def _create_status_section(self, parent: tk.Frame) -> None:
        """Create the status display section."""
        status_frame: tk.LabelFrame = tk.LabelFrame(
            master=parent,
            text="Sensor Status",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10,
        )
        status_frame.pack(fill=tk.X, pady=5)

        # Raw value
        raw_label: tk.Label = tk.Label(
            master=status_frame, text="Raw Value:", font=("Arial", 9), anchor="w"
        )
        raw_label.grid(row=0, column=0, sticky="w", padx=5, pady=5)

        self.raw_value_display: tk.Label = tk.Label(
            master=status_frame,
            text=self.current_raw_value,
            font=("Arial", 11, "bold"),
            fg="blue",
            anchor="w",
        )
        self.raw_value_display.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        # Change percent
        change_label: tk.Label = tk.Label(
            master=status_frame, text="Change %:", font=("Arial", 9), anchor="w"
        )
        change_label.grid(row=1, column=0, sticky="w", padx=5, pady=5)

        self.change_display: tk.Label = tk.Label(
            master=status_frame,
            text=self.current_change_percent,
            font=("Arial", 11, "bold"),
            fg="cyan",
            anchor="w",
        )
        self.change_display.grid(row=1, column=1, sticky="w", padx=5, pady=5)

        # Current state
        state_label: tk.Label = tk.Label(
            master=status_frame, text="State:", font=("Arial", 9), anchor="w"
        )
        state_label.grid(row=2, column=0, sticky="w", padx=5, pady=5)

        self.state_display: tk.Label = tk.Label(
            master=status_frame,
            text=self.current_state,
            font=("Arial", 11, "bold"),
            fg="green",
            anchor="w",
        )
        self.state_display.grid(row=2, column=1, sticky="w", padx=5, pady=5)

        # Health state
        health_label: tk.Label = tk.Label(
            master=status_frame, text="Health:", font=("Arial", 9), anchor="w"
        )
        health_label.grid(row=3, column=0, sticky="w", padx=5, pady=5)

        self.health_display: tk.Label = tk.Label(
            master=status_frame,
            text=self.current_health,
            font=("Arial", 11, "bold"),
            fg="orange",
            anchor="w",
        )
        self.health_display.grid(row=3, column=1, sticky="w", padx=5, pady=5)

    def _create_control_section(self, parent: tk.Frame) -> None:
        """Create the control buttons section."""
        control_frame: tk.LabelFrame = tk.LabelFrame(
            master=parent,
            text="Control",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10,
        )
        control_frame.pack(fill=tk.X, pady=5)

        # Init/Deinit buttons
        init_deinit_frame: tk.Frame = tk.Frame(master=control_frame)
        init_deinit_frame.pack(side=tk.LEFT, padx=5)

        self.init_button: tk.Button = tk.Button(
            master=init_deinit_frame,
            text="Init",
            command=self.leakage_init,
            width=10,
        )
        self.init_button.pack(side=tk.LEFT, padx=2)

        self.deinit_button: tk.Button = tk.Button(
            master=init_deinit_frame,
            text="Deinit",
            command=self.leakage_deinit,
            width=10,
        )
        self.deinit_button.pack(side=tk.LEFT, padx=2)

    def leakage_init(self) -> None:
        """Initialize leakage sensor, calibrate, and enable monitoring in one go."""
        try:
            if not self.serial_terminal.serial.is_connected():
                print("Serial port not connected")
                return

            # Get selected GPIO
            self.leakage_gpio = self.gpio_combobox.get()
            self._save_leakage_config()

            # Send init command
            command = f"leakage init {self.leakage_gpio}\n"
            self.serial_terminal.serial.send(command)
            self.leakage_initialized = True
            print(f"Leakage sensor initialized on {self.leakage_gpio}")

            # Get calibration scans value
            try:
                scans = int(self.calib_scans_var.get())
            except ValueError:
                scans = 3
                self.calib_scans_var.set("3")

            # Send calibrate command
            command = f"leakage calibrate {scans}\n"
            self.serial_terminal.serial.send(command)
            print(f"Leakage sensor calibration started ({scans} scans)")

            # Send enable command
            command = "leakage enable\n"
            self.serial_terminal.serial.send(command)
            self.leakage_monitoring = True
            print("Leakage sensor monitoring enabled")
        except Exception as e:
            print(f"Error initializing leakage sensor: {e}")

    def leakage_deinit(self) -> None:
        """Disable monitoring and deinitialize leakage sensor in one go."""
        try:
            if not self.serial_terminal.serial.is_connected():
                print("Serial port not connected")
                return

            # Send disable command
            command = "leakage disable\n"
            self.serial_terminal.serial.send(command)
            self.leakage_monitoring = False
            print("Leakage sensor monitoring disabled")

            # Send deinit command
            command = "leakage deinit\n"
            self.serial_terminal.serial.send(command)
            self.leakage_initialized = False
            print("Leakage sensor deinitialized")
        except Exception as e:
            print(f"Error deinitializing leakage sensor: {e}")

    def _save_leakage_config(self) -> None:
        """Save leakage configuration to config file."""
        try:
            config = get_config_manager()
            config.set("leakage.gpio", self.leakage_gpio)
            try:
                scans = int(self.calib_scans_var.get())
                config.set("leakage.calibration_scans", scans)
            except ValueError:
                pass
            config.save()
        except Exception as e:
            print(f"Error saving leakage config: {e}")

    def update_connection_state(self) -> None:
        """Update button states based on connection state."""
        is_connected = self.serial_terminal.serial.is_connected()
        self.init_button.config(state="normal" if is_connected else "disabled")
        self.deinit_button.config(state="normal" if is_connected else "disabled")

    def on_leakage_status_event(self, timestamp: str, data: str) -> None:
        """Callback for leakage status event.

        Data format: "<raw_value> <change_percent> <current_state> <health_state>"
        Example: "2458  15.67 0 0"
        """
        try:
            values = data.split()
            if len(values) >= 4:
                raw_val = int(float(values[0]))
                change_pct = float(values[1])
                state_val = int(values[2])
                health_val = int(values[3])

                # Update display
                self.current_raw_value = str(raw_val)
                self.raw_value_display.config(text=self.current_raw_value)

                self.current_change_percent = f"{change_pct:.2f}%"
                self.change_display.config(text=self.current_change_percent)

                # State: 0=Dry, 1=Moist, 2=Wet, 3=Critical
                state_map = {0: "Dry", 1: "Moist", 2: "Wet", 3: "Critical"}
                self.current_state = state_map.get(state_val, f"Unknown({state_val})")
                if state_val == 0:
                    state_color = "green"
                elif state_val == 1:
                    state_color = "yellow"
                elif state_val == 2:
                    state_color = "orange"
                else:
                    state_color = "red"
                self.state_display.config(text=self.current_state, fg=state_color)

                # Health: 0=OK, 1=Stuck, 2=Fault
                health_map = {0: "OK", 1: "Stuck", 2: "Fault"}
                self.current_health = health_map.get(
                    health_val, f"Unknown({health_val})"
                )
                health_color = (
                    "green"
                    if health_val == 0
                    else ("orange" if health_val == 1 else "red")
                )
                self.health_display.config(text=self.current_health, fg=health_color)

                # print(f"Leakage status: raw={raw_val}, change={change_pct:.2f}%, state={self.current_state}, health={self.current_health}")
        except Exception as e:
            print(f"Error processing leakage status event: {e}")

    def on_window_close(self) -> None:
        """Handle window close."""
        self._save_leakage_config()
        self.window.destroy()
