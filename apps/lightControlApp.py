"""Light Control application module."""

import threading
import tkinter as tk
from tkinter import ttk


class LightControlApp:
    """Application for controlling a single LED light."""
    
    GPIO_OPTIONS: list[str] = [f"GPIO{i}" for i in range(22)] + [
        f"GPIO{i}" for i in range(26, 49)
    ]
    FREQUENCY_OPTIONS: list[str] = [
        "50Hz", "60Hz", "100Hz", "120Hz", "440Hz", "1000Hz",
        "10000Hz", "44100Hz", "48000Hz", "96000Hz"
    ]
    GAMMA_OPTIONS: list[str] = [
        f"{i:.1f}" for i in [round(x * 0.1, 1) for x in range(10, 31)]
    ]

    def __init__(self, parent) -> None:
        self.parent = parent
        self.window: tk.Toplevel = tk.Toplevel(parent.master)
        self.window.title("Light Control")
        self.window.geometry("750x170")
        
        self.window.protocol("WM_DELETE_WINDOW", self.on_window_close)
        
        self.light_initialized: bool = False
        self.light_power_pending: float | None = None
        self.light_power_send_scheduled: bool = False
        self.current_gamma: float = 2.3
        
        main_frame: tk.Frame = tk.Frame(master=self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self._create_light_section(main_frame)
        
        self.update_connection_state()

    def _create_light_section(self, parent: tk.Frame) -> None:
        """Create the LED Light control section."""
        light_frame: tk.LabelFrame = tk.LabelFrame(
            master=parent,
            text="LED Light",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10,
        )
        light_frame.pack(fill=tk.X, pady=5)
        
        config_frame: tk.Frame = tk.Frame(master=light_frame)
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
        self.gpio_combobox.set("GPIO14")
        self.gpio_combobox.pack(side=tk.LEFT, padx=2)
        
        # Frequency selection
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
        
        # Gamma selection
        gamma_frame: tk.Frame = tk.Frame(master=config_frame)
        gamma_frame.pack(side=tk.LEFT, padx=5)
        
        gamma_label: tk.Label = tk.Label(master=gamma_frame, text="Gamma:", anchor="w")
        gamma_label.pack(side=tk.LEFT, padx=2)
        
        self.gamma_combobox: ttk.Combobox = ttk.Combobox(
            master=gamma_frame,
            values=self.GAMMA_OPTIONS,
            state="readonly",
            width=8,
        )
        self.gamma_combobox.set("2.3")
        self.gamma_combobox.pack(side=tk.LEFT, padx=2)
        self.gamma_combobox.bind("<<ComboboxSelected>>", self.on_gamma_changed)
        
        # Init and Deinit buttons
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
        
        # Power level slider
        power_frame: tk.Frame = tk.Frame(master=light_frame)
        power_frame.pack(fill=tk.X, pady=(10, 5))
        
        power_label: tk.Label = tk.Label(master=power_frame, text="Power Level:", anchor="w")
        power_label.pack(side=tk.LEFT, padx=5)
        
        slider_container: tk.Frame = tk.Frame(master=power_frame)
        slider_container.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        self.power_slider: tk.Scale = tk.Scale(
            master=slider_container,
            from_=0,
            to=7,
            orient=tk.HORIZONTAL,
            command=lambda val: self._on_power_slider_changed(int(val)),
            state="disabled",
        )
        self.power_slider.set(0)
        self.power_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        slider_container.bind("<Button-3>", lambda event: self._reset_power_slider())
        
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
        
        self.power_value_label.bind("<Button-1>", lambda event: self._reset_power_slider())
        self.power_value_label.bind("<Button-2>", lambda event: self._reset_power_slider())
        self.power_value_label.bind("<Button-3>", lambda event: self._reset_power_slider())

    def _level_to_pwm(self, level: int) -> int:
        """Convert power level (0-7) to PWM value (0-256) using gamma correction."""
        normalized = level / 7.0
        gamma_corrected = pow(normalized, self.current_gamma)
        pwm_value = int(gamma_corrected * 256)
        return min(pwm_value, 256)

    def on_gamma_changed(self, event: tk.Event | None = None) -> None:
        """Handle gamma value change."""
        try:
            gamma_str = self.gamma_combobox.get()
            self.current_gamma = float(gamma_str)
            if self.light_initialized:
                level = int(self.power_slider.get())
                pwm_value = self._level_to_pwm(level)
                self.power_value_label.config(text=f"{pwm_value}/256")
        except ValueError:
            print("Invalid gamma value")

    def _on_power_slider_changed(self, level: int) -> None:
        """Handle power slider change with throttling."""
        pwm_value = self._level_to_pwm(level)
        
        self.power_value_label.config(text=f"{pwm_value}/256")
        
        self.light_power_pending = pwm_value
        
        if not self.light_power_send_scheduled:
            self.light_power_send_scheduled = True
            self.parent.master.after(75, self._send_pending_power)

    def _send_pending_power(self) -> None:
        """Send the latest pending power value for the light."""
        if self.light_power_pending is not None:
            pwm_value = self.light_power_pending
            command = f"light set {pwm_value}"
            threading.Thread(
                target=self._send_command,
                args=(command,),
                daemon=True
            ).start()
            self.light_power_pending = None
        
        self.light_power_send_scheduled = False

    def _reset_power_slider(self) -> None:
        """Reset power slider to zero."""
        self.power_slider.set(0)

    def _send_command(self, command: str) -> None:
        """Send a command to serial via parent."""
        try:
            if not command.endswith("\n"):
                command += "\n"
            
            if self.parent.serial.is_connected():
                self.parent.serial.send(command)
                threading.Thread(
                    target=self.parent._async_log_and_display,
                    args=(command,),
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
        freq_num = freq_str.replace("Hz", "")
        
        config_command = f"light config {gpio_num} {freq_num}"
        self.parent.master.after(0, lambda cmd=config_command: self._send_command(cmd))
        
        freq_command = f"light freq {freq_num}"
        self.parent.master.after(200, lambda cmd=freq_command: self._send_command(cmd))
        
        self.light_initialized = True
        self.parent.master.after(400, self.update_light_config_state)
        self.parent.master.after(400, self.update_connection_state)

    def deinit_light(self) -> None:
        """Send deinit command for the light."""
        set_zero_command = "light set 0"
        self.parent.master.after(0, lambda cmd=set_zero_command: self._send_command(cmd))
        
        delete_command = "light delete"
        self.parent.master.after(200, lambda cmd=delete_command: self._send_command(cmd))
        
        self.light_initialized = False
        self.power_slider.set(0)
        self.parent.master.after(400, self.update_light_config_state)
        self.parent.master.after(400, self.update_connection_state)

    def update_light_config_state(self) -> None:
        """Update UI state based on initialization status."""
        self.gpio_combobox.config(state="disabled" if self.light_initialized else "readonly")
        self.frequency_combobox.config(state="disabled" if self.light_initialized else "readonly")
        self.power_slider.config(state="normal" if self.light_initialized else "disabled")

    def update_connection_state(self) -> None:
        """Update button state based on serial connection and initialization."""
        is_connected = self.parent.serial.is_connected()
        
        if not is_connected:
            self.init_button.config(state="disabled")
            self.deinit_button.config(state="disabled")
        else:
            self.init_button.config(state="normal" if not self.light_initialized else "disabled")
            self.deinit_button.config(state="normal" if self.light_initialized else "disabled")

    def on_window_close(self) -> None:
        """Hide window instead of closing it."""
        self.window.withdraw()
