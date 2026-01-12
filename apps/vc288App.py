"""VC288 Voltage/Current Sensor application module."""

import tkinter as tk
from tkinter import ttk

from configManager import get_config_manager

# Load VC288 configuration from config
config = get_config_manager()


class VC288App:
    """Application for VC288 voltage/current sensor monitoring."""

    GPIO_OPTIONS: list[str] = [f"GPIO{i}" for i in range(22)] + [
        f"GPIO{i}" for i in range(26, 49)
    ]

    def __init__(self, parent) -> None:
        self.parent = parent
        self.window: tk.Toplevel = tk.Toplevel(parent.master)
        self.window.title("VC288 Sensor")
        self.window.geometry("600x400")

        self.window.protocol("WM_DELETE_WINDOW", self.on_window_close)

        # Load VC288 config
        self.vc288_gpio = config.get("vc288.gpio", "GPIO13")
        self.vc288_voltage_slope: float = config.get("vc288.voltage_slope", 1.0)
        self.vc288_voltage_offset: float = config.get("vc288.voltage_offset", 0.0)
        self.vc288_voltage_x2: float = config.get("vc288.voltage_x2", 0.0)
        self.vc288_current_slope: float = config.get("vc288.current_slope", 1.0)
        self.vc288_current_offset: float = config.get("vc288.current_offset", 0.0)
        self.vc288_current_x2: float = config.get("vc288.current_x2", 0.0)
        self.vc288_initialized: bool = False

        # Register event callbacks with the serial terminal
        self.serial_terminal = parent
        self.serial_terminal.register_event_callback("0x60", self.on_voltage_event)
        self.serial_terminal.register_event_callback("0x61", self.on_current_event)

        # Register connection state callback
        self.serial_terminal.register_connection_state_callback(
            self.update_connection_state
        )

        # Current sensor values
        self.current_voltage: str = "0.00 V"
        self.current_current: str = "0.00 A"

        main_frame: tk.Frame = tk.Frame(master=self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self._create_config_section(main_frame)
        self._create_display_section(main_frame)

        # Auto-size window to fit content
        self.window.update_idletasks()
        width = main_frame.winfo_reqwidth() + 20
        height = main_frame.winfo_reqheight() + 20
        self.window.geometry(f"{width}x{height}")

        self.update_connection_state()

    def _create_config_section(self, parent: tk.Frame) -> None:
        """Create the configuration section with GPIO and Init/Deinit buttons."""
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
        self.gpio_combobox.set(self.vc288_gpio)
        self.gpio_combobox.pack(side=tk.LEFT, padx=2)

        # Voltage slope
        voltage_slope_frame: tk.Frame = tk.Frame(master=config_frame)
        voltage_slope_frame.pack(side=tk.LEFT, padx=5)

        voltage_slope_label: tk.Label = tk.Label(
            master=voltage_slope_frame, text="V Slope:", anchor="w"
        )
        voltage_slope_label.pack(side=tk.LEFT, padx=2)

        self.voltage_slope_var = tk.StringVar(value=f"{self.vc288_voltage_slope:.6f}")
        self.voltage_slope_entry: tk.Entry = tk.Entry(
            master=voltage_slope_frame,
            textvariable=self.voltage_slope_var,
            width=10,
        )
        self.voltage_slope_entry.pack(side=tk.LEFT, padx=2)
        self.voltage_slope_entry.bind("<Return>", lambda e: self._save_vc288_config())

        # Voltage offset
        voltage_offset_frame: tk.Frame = tk.Frame(master=config_frame)
        voltage_offset_frame.pack(side=tk.LEFT, padx=5)

        voltage_offset_label: tk.Label = tk.Label(
            master=voltage_offset_frame, text="V Offset:", anchor="w"
        )
        voltage_offset_label.pack(side=tk.LEFT, padx=2)

        self.voltage_offset_var = tk.StringVar(value=f"{self.vc288_voltage_offset:.6f}")
        self.voltage_offset_entry: tk.Entry = tk.Entry(
            master=voltage_offset_frame,
            textvariable=self.voltage_offset_var,
            width=10,
        )
        self.voltage_offset_entry.pack(side=tk.LEFT, padx=2)
        self.voltage_offset_entry.bind("<Return>", lambda e: self._save_vc288_config())

        # Voltage x2
        voltage_x2_frame: tk.Frame = tk.Frame(master=config_frame)
        voltage_x2_frame.pack(side=tk.LEFT, padx=5)

        voltage_x2_label: tk.Label = tk.Label(
            master=voltage_x2_frame, text="V X2:", anchor="w"
        )
        voltage_x2_label.pack(side=tk.LEFT, padx=2)

        self.voltage_x2_var = tk.StringVar(value=f"{self.vc288_voltage_x2:.9f}")
        self.voltage_x2_entry: tk.Entry = tk.Entry(
            master=voltage_x2_frame,
            textvariable=self.voltage_x2_var,
            width=12,
        )
        self.voltage_x2_entry.pack(side=tk.LEFT, padx=2)
        self.voltage_x2_entry.bind("<Return>", lambda e: self._save_vc288_config())

        # Current slope
        current_slope_frame: tk.Frame = tk.Frame(master=config_frame)
        current_slope_frame.pack(side=tk.LEFT, padx=5)

        current_slope_label: tk.Label = tk.Label(
            master=current_slope_frame, text="A Slope:", anchor="w"
        )
        current_slope_label.pack(side=tk.LEFT, padx=2)

        self.current_slope_var = tk.StringVar(value=f"{self.vc288_current_slope:.6f}")
        self.current_slope_entry: tk.Entry = tk.Entry(
            master=current_slope_frame,
            textvariable=self.current_slope_var,
            width=10,
        )
        self.current_slope_entry.pack(side=tk.LEFT, padx=2)
        self.current_slope_entry.bind("<Return>", lambda e: self._save_vc288_config())

        # Current offset
        current_offset_frame: tk.Frame = tk.Frame(master=config_frame)
        current_offset_frame.pack(side=tk.LEFT, padx=5)

        current_offset_label: tk.Label = tk.Label(
            master=current_offset_frame, text="A Offset:", anchor="w"
        )
        current_offset_label.pack(side=tk.LEFT, padx=2)

        self.current_offset_var = tk.StringVar(value=f"{self.vc288_current_offset:.6f}")
        self.current_offset_entry: tk.Entry = tk.Entry(
            master=current_offset_frame,
            textvariable=self.current_offset_var,
            width=10,
        )
        self.current_offset_entry.pack(side=tk.LEFT, padx=2)
        self.current_offset_entry.bind("<Return>", lambda e: self._save_vc288_config())

        # Current x2
        current_x2_frame: tk.Frame = tk.Frame(master=config_frame)
        current_x2_frame.pack(side=tk.LEFT, padx=5)

        current_x2_label: tk.Label = tk.Label(
            master=current_x2_frame, text="A X2:", anchor="w"
        )
        current_x2_label.pack(side=tk.LEFT, padx=2)

        self.current_x2_var = tk.StringVar(value=f"{self.vc288_current_x2:.9f}")
        self.current_x2_entry: tk.Entry = tk.Entry(
            master=current_x2_frame,
            textvariable=self.current_x2_var,
            width=12,
        )
        self.current_x2_entry.pack(side=tk.LEFT, padx=2)
        self.current_x2_entry.bind("<Return>", lambda e: self._save_vc288_config())

        # Init and Deinit buttons
        button_frame: tk.Frame = tk.Frame(master=config_frame)
        button_frame.pack(side=tk.RIGHT, padx=5)

        self.init_button: tk.Button = tk.Button(
            master=button_frame,
            text="Init",
            command=self.init_sensor,
            width=10,
        )
        self.init_button.pack(side=tk.LEFT, padx=2)

        self.deinit_button: tk.Button = tk.Button(
            master=button_frame,
            text="Deinit",
            command=self.deinit_sensor,
            width=10,
        )
        self.deinit_button.pack(side=tk.LEFT, padx=2)

    def _create_display_section(self, parent: tk.Frame) -> None:
        """Create the display section with large voltage and current labels."""
        display_frame: tk.LabelFrame = tk.LabelFrame(
            master=parent,
            text="Sensor Readings",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10,
        )
        display_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Voltage display
        voltage_container: tk.Frame = tk.Frame(master=display_frame)
        voltage_container.pack(fill=tk.X, pady=20)

        voltage_label: tk.Label = tk.Label(
            master=voltage_container, text="Voltage:", font=("Arial", 12, "bold")
        )
        voltage_label.pack(side=tk.LEFT, padx=10)

        self.voltage_display: tk.Label = tk.Label(
            master=voltage_container,
            text=self.current_voltage,
            font=("Arial", 32, "bold"),
            fg="#FF6B6B",
            bg="#F0F0F0",
            relief=tk.SUNKEN,
            bd=3,
            width=15,
            anchor="center",
        )
        self.voltage_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

        # Current display
        current_container: tk.Frame = tk.Frame(master=display_frame)
        current_container.pack(fill=tk.X, pady=20)

        current_label: tk.Label = tk.Label(
            master=current_container, text="Current:", font=("Arial", 12, "bold")
        )
        current_label.pack(side=tk.LEFT, padx=10)

        self.current_display: tk.Label = tk.Label(
            master=current_container,
            text=self.current_current,
            font=("Arial", 32, "bold"),
            fg="#4ECDC4",
            bg="#F0F0F0",
            relief=tk.SUNKEN,
            bd=3,
            width=15,
            anchor="center",
        )
        self.current_display.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)

    def _save_vc288_config(self) -> None:
        """Save VC288 configuration to config file."""
        try:
            config.set("vc288.gpio", self.gpio_combobox.get())
            # Save slopes, offsets, and x2 from UI
            try:
                self.vc288_voltage_slope = float(self.voltage_slope_var.get())
                self.vc288_voltage_offset = float(self.voltage_offset_var.get())
                self.vc288_voltage_x2 = float(self.voltage_x2_var.get())
                self.vc288_current_slope = float(self.current_slope_var.get())
                self.vc288_current_offset = float(self.current_offset_var.get())
                self.vc288_current_x2 = float(self.current_x2_var.get())
            except ValueError:
                print("Invalid slope/offset/x2 values, using previous values")
            config.set("vc288.voltage_slope", self.vc288_voltage_slope)
            config.set("vc288.voltage_offset", self.vc288_voltage_offset)
            config.set("vc288.voltage_x2", self.vc288_voltage_x2)
            config.set("vc288.current_slope", self.vc288_current_slope)
            config.set("vc288.current_offset", self.vc288_current_offset)
            config.set("vc288.current_x2", self.vc288_current_x2)
            config.save()
            print(
                f"[DEBUG] Saved VC288 config: GPIO={self.gpio_combobox.get()}, V_slope={self.vc288_voltage_slope}, V_offset={self.vc288_voltage_offset}, V_x2={self.vc288_voltage_x2}, A_slope={self.vc288_current_slope}, A_offset={self.vc288_current_offset}, A_x2={self.vc288_current_x2}"
            )
        except Exception as e:
            print(f"Error saving VC288 config: {e}")

    def init_sensor(self) -> None:
        """Send init command for the VC288 sensor with GPIO."""
        if self.gpio_combobox is None:
            print("Error: GPIO combobox is not initialized")
            return

        gpio_str: str = self.gpio_combobox.get()
        gpio_num = int(gpio_str.replace("GPIO", ""))

        init_command = f"vc288 init {gpio_num}"
        self.parent.master.after(0, lambda cmd=init_command: self._send_command(cmd))

        self.vc288_initialized = True
        self.parent.master.after(200, self._save_vc288_config)
        self.parent.master.after(400, self.update_sensor_config_state)
        self.parent.master.after(400, self.update_connection_state)

    def deinit_sensor(self) -> None:
        """Send deinit command for the VC288 sensor."""
        deinit_command = "vc288 deinit"
        self.parent.master.after(0, lambda cmd=deinit_command: self._send_command(cmd))

        self.vc288_initialized = False
        self.current_voltage = "0.00 V"
        self.current_current = "0.00 A"
        self.voltage_display.config(text=self.current_voltage)
        self.current_display.config(text=self.current_current)
        self.parent.master.after(400, self.update_sensor_config_state)
        self.parent.master.after(400, self.update_connection_state)

    def update_sensor_config_state(self) -> None:
        """Update UI state based on initialization status."""
        self.gpio_combobox.config(
            state="disabled" if self.vc288_initialized else "readonly"
        )
        init_state = "disabled" if self.vc288_initialized else "normal"
        deinit_state = "normal" if self.vc288_initialized else "disabled"

        self.init_button.config(state=init_state)
        self.deinit_button.config(state=deinit_state)

    def update_connection_state(self) -> None:
        """Update UI state based on connection status."""
        is_connected = self.serial_terminal.serial.is_connected()

        if not is_connected:
            self.init_button.config(state="disabled")
            self.deinit_button.config(state="disabled")
        else:
            init_state = "disabled" if self.vc288_initialized else "normal"
            deinit_state = "normal" if self.vc288_initialized else "disabled"
            self.init_button.config(state=init_state)
            self.deinit_button.config(state=deinit_state)

    def _send_command(self, command: str) -> None:
        """Send a command via serial."""
        try:
            if self.serial_terminal.serial.is_connected():
                self.serial_terminal.serial.send(command + "\n")
                self.serial_terminal._async_log_and_display(command)
            else:
                print("Serial port not connected")
        except Exception as e:
            print(f"Error sending command: {e}")

    def on_voltage_event(self, timestamp: str, data: str) -> None:
        """Callback for voltage event (event 0x60).

        Args:
            timestamp: Timestamp string (e.g., "       15765 ms")
            data: Voltage value (e.g., "8.24")
        """
        try:
            # Parse voltage data - expecting format like "8.24"
            voltage_val = float(data.strip())
            # Update slope, offset and x2 from UI
            try:
                self.vc288_voltage_slope = float(self.voltage_slope_var.get())
                self.vc288_voltage_offset = float(self.voltage_offset_var.get())
                self.vc288_voltage_x2 = float(self.voltage_x2_var.get())
            except ValueError:
                pass
            # Apply calibration: value_calibrated = offset + slope * value_raw + x2 * value_raw^2
            voltage_calibrated = self.vc288_voltage_offset + self.vc288_voltage_slope * voltage_val + self.vc288_voltage_x2 * (voltage_val ** 2)
            self.current_voltage = f"{voltage_calibrated:.2f} V"
            self.voltage_display.config(text=self.current_voltage)
            # print(f"Voltage: {self.current_voltage} (raw: {voltage_val:.2f}, slope: {self.vc288_voltage_slope}, offset: {self.vc288_voltage_offset}, x2: {self.vc288_voltage_x2}, ts: {timestamp})")
        except ValueError:
            print(f"Invalid voltage data: {data}")

    def on_current_event(self, timestamp: str, data: str) -> None:
        """Callback for current event (event 0x61).

        Args:
            timestamp: Timestamp string (e.g., "       15765 ms")
            data: Current value (e.g., "0.340")
        """
        try:
            # Parse current data - expecting format like "0.340"
            current_val = float(data.strip())
            # Update slope, offset and x2 from UI
            try:
                self.vc288_current_slope = float(self.current_slope_var.get())
                self.vc288_current_offset = float(self.current_offset_var.get())
                self.vc288_current_x2 = float(self.current_x2_var.get())
            except ValueError:
                pass
            # Apply calibration: value_calibrated = offset + slope * value_raw + x2 * value_raw^2
            current_calibrated = self.vc288_current_offset + self.vc288_current_slope * current_val + self.vc288_current_x2 * (current_val ** 2)
            self.current_current = f"{current_calibrated:.3f} A"
            self.current_display.config(text=self.current_current)
            # print(f"Current: {self.current_current} (raw: {current_val:.2f}, slope: {self.vc288_current_slope}, offset: {self.vc288_current_offset}, x2: {self.vc288_current_x2})")
        except ValueError:
            print(f"Invalid current data: {data}")

    def on_window_close(self) -> None:
        """Handle window close."""
        # Save configuration
        self._save_vc288_config()
        self.window.destroy()
