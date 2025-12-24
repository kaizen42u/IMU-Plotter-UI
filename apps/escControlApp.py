"""ESC Control application module."""

import threading
import tkinter as tk
from tkinter import ttk
from typing import cast


class ESCControlApp:
    """Application for controlling Electronic Speed Controllers."""
    
    GPIO_OPTIONS: list[str] = [f"GPIO{i}" for i in range(22)] + [
        f"GPIO{i}" for i in range(26, 49)
    ]
    FREQUENCY_OPTIONS: list[str] = ["50Hz", "100Hz", "200Hz", "300Hz"]
    DIRECTION_OPTIONS: list[str] = ["Normal", "Inverted"]
    
    DEFAULT_ESC_CONFIG: list[dict[str, str | list[int]]] = [
        {
            "gpio": "GPIO9",
            "direction": "Normal",
            "calibration": [1000, 1442, 1500, 1586, 2000],
        },
        {
            "gpio": "GPIO10",
            "direction": "Inverted",
            "calibration": [1000, 1444, 1500, 1551, 2000],
        },
        {
            "gpio": "GPIO11",
            "direction": "Normal",
            "calibration": [1000, 1440, 1500, 1556, 2000],
        },
        {
            "gpio": "GPIO12",
            "direction": "Inverted",
            "calibration": [1000, 1492, 1500, 1514, 2000],
        },
    ]

    def __init__(self, parent) -> None:
        self.parent = parent
        self.window: tk.Toplevel = tk.Toplevel(parent.master)
        self.window.title("ESC Control")
        self.window.geometry("700x820")
        
        self.window.protocol("WM_DELETE_WINDOW", self.on_window_close)
        
        self.esc_configs: list[dict[str, str | list[int]]] = [
            self.DEFAULT_ESC_CONFIG[i].copy() for i in range(4)
        ]
        
        self.esc_gpio_comboboxes: list[ttk.Combobox | None] = [None] * 4
        self.esc_direction_comboboxes: list[ttk.Combobox | None] = [None] * 4
        self.esc_initialized: list[bool] = [False] * 4
        self.esc_selected: list[tk.BooleanVar] = [
            tk.BooleanVar(value=True) for _ in range(4)
        ]
        self.esc_calibration_entries: list[list[tk.Entry]] = []
        self.esc_power_sliders: list[tk.Scale] = []
        self.esc_power_value_labels: list[tk.Label] = []
        
        self.esc_power_pending: list[float | None] = [None] * 4
        self.esc_power_send_scheduled: list[bool] = [False] * 4
        
        main_frame: tk.Frame = tk.Frame(master=self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        self._create_common_section(main_frame)
        
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
        
        settings_frame: tk.Frame = tk.Frame(master=common_frame)
        settings_frame.pack(fill=tk.X, pady=5)
        
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
        self.frequency_combobox.set("300Hz")
        self.frequency_combobox.pack(side=tk.LEFT, padx=2)
        
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
        
        self.update_connection_state()

    def on_window_close(self) -> None:
        """Hide window instead of closing it."""
        self.window.withdraw()

    def init_escs(self) -> None:
        """Send init commands for enabled ESCs."""
        command_delay = 0
        
        for index in range(4):
            esc_id = index + 1
            
            if not self.esc_selected[index].get():
                continue
            
            if self.esc_initialized[index]:
                continue
            
            if self.esc_gpio_comboboxes[index] is None:
                continue
            
            gpio_combobox: ttk.Combobox = cast(
                ttk.Combobox, self.esc_gpio_comboboxes[index]
            )
            direction_combobox: ttk.Combobox = cast(
                ttk.Combobox, self.esc_direction_comboboxes[index]
            )
            gpio_str: str = gpio_combobox.get()
            direction_str: str = direction_combobox.get()
            
            gpio_num = int(gpio_str.replace("GPIO", ""))
            direction_num = 0 if direction_str == "Normal" else 1
            
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
            
            freq_str: str = self.frequency_combobox.get()
            freq_num = freq_str.replace("Hz", "")
            freq_command = f"esc freq {freq_num}"
            self.parent.master.after(
                command_delay, lambda cmd=freq_command: self._send_command(cmd)
            )
            command_delay += 200
            
            init_command = f"esc {esc_id} init {gpio_num}"
            self.parent.master.after(
                command_delay,
                lambda cmd=init_command, idx=index: self._send_init_command(cmd, idx),
            )
            command_delay += 200
            
            dir_command = f"esc {esc_id} dir {direction_num}"
            self.parent.master.after(
                command_delay, lambda cmd=dir_command: self._send_command(cmd)
            )
            command_delay += 200
            
            cali_command = f"esc {esc_id} cali {calib_values[0]} {calib_values[1]} {calib_values[2]} {calib_values[3]} {calib_values[4]}"
            self.parent.master.after(
                command_delay,
                lambda cmd=cali_command: self._send_command(cmd),
            )
            command_delay += 200
            
            power_sequence = [0.00, -0.01, 0.00, 0.01, 0.00]
            for power_val in power_sequence:
                pw_command = f"esc {esc_id} pw {power_val:.2f}"
                self.parent.master.after(
                    command_delay,
                    lambda cmd=pw_command: self._send_command(cmd),
                )
                command_delay += 750

    def _send_init_command(self, command: str, index: int) -> None:
        """Send init command and mark ESC as initialized."""
        self._send_command(command)
        self.esc_initialized[index] = True
        if index < len(self.esc_power_sliders):
            self.esc_power_sliders[index].set(0)
        self.update_esc_config_state(index)
        self.update_connection_state()

    def deinit_escs(self) -> None:
        """Send deinit commands for enabled ESCs."""
        command_delay = 0
        
        for index in range(4):
            esc_id = index + 1
            
            if not self.esc_selected[index].get():
                continue
            
            if not self.esc_initialized[index]:
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
        self._send_command(command)
        self.esc_initialized[index] = False
        if index < len(self.esc_power_sliders):
            self.esc_power_sliders[index].set(0)
        self.update_esc_config_state(index)
        self.update_connection_state()

    def update_esc_config_state(self, index: int) -> None:
        """Update UI state for a specific ESC based on initialization status."""
        is_initialized = self.esc_initialized[index]
        
        if self.esc_gpio_comboboxes[index] is not None:
            gpio_box: ttk.Combobox = cast(ttk.Combobox, self.esc_gpio_comboboxes[index])
            gpio_box.config(state="disabled" if is_initialized else "readonly")
        
        if self.esc_direction_comboboxes[index] is not None:
            direction_box: ttk.Combobox = cast(
                ttk.Combobox, self.esc_direction_comboboxes[index]
            )
            direction_box.config(state="disabled" if is_initialized else "readonly")
        
        if hasattr(self, "esc_calibration_entries") and index < len(
            self.esc_calibration_entries
        ):
            for entry in self.esc_calibration_entries[index]:
                entry.config(state="disabled" if is_initialized else "normal")
        
        if hasattr(self, "esc_power_sliders") and index < len(self.esc_power_sliders):
            self.esc_power_sliders[index].config(
                state="normal" if is_initialized else "disabled"
            )
        
        any_initialized = any(self.esc_initialized)
        self.frequency_combobox.config(
            state="disabled" if any_initialized else "readonly"
        )

    def _reset_power_slider(self, index: int) -> None:
        """Reset power slider to zero."""
        if hasattr(self, "esc_power_sliders") and index < len(self.esc_power_sliders):
            self.esc_power_sliders[index].set(0)

    def update_connection_state(self) -> None:
        """Update ESC control button state based on serial connection."""
        is_connected = self.parent.serial.is_connected()
        
        selected_indices = [i for i in range(4) if self.esc_selected[i].get()]
        
        if not is_connected:
            self.init_escs_button.config(state="disabled")
            self.deinit_escs_button.config(state="disabled")
        else:
            has_uninitialized_selected = any(
                not self.esc_initialized[i] for i in selected_indices
            )
            has_initialized_selected = any(
                self.esc_initialized[i] for i in selected_indices
            )
            
            self.init_escs_button.config(
                state="normal" if has_uninitialized_selected else "disabled"
            )
            self.deinit_escs_button.config(
                state="normal" if has_initialized_selected else "disabled"
            )

    def _on_power_slider_changed(self, index: int, slider_value: int) -> None:
        """Handle power slider change with throttling."""
        power: float = slider_value / 100.0
        
        if hasattr(self, "esc_power_value_labels") and index < len(
            self.esc_power_value_labels
        ):
            label: tk.Label = self.esc_power_value_labels[index]
            label.config(text=f"{power:.2f}")
            
            if power == 0.0:
                label.config(bg="#90EE90")
            elif power > 0.0:
                label.config(bg="#FFFF00")
            else:
                label.config(bg="#FFA500")
        
        self.esc_power_pending[index] = power
        
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
                target=self._send_command, args=(command,), daemon=True
            ).start()
            self.esc_power_pending[index] = None
        
        self.esc_power_send_scheduled[index] = False

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
        
        config_frame: tk.Frame = tk.Frame(master=section_frame)
        config_frame.pack(fill=tk.X, pady=5)
        
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
        
        toggle_checkbox: tk.Checkbutton = tk.Checkbutton(
            master=config_frame,
            text="Selected",
            variable=self.esc_selected[index],
            anchor="w",
            command=self.update_connection_state,
        )
        toggle_checkbox.pack(side=tk.RIGHT, padx=5)
        
        self.esc_gpio_comboboxes[index] = gpio_combobox
        self.esc_direction_comboboxes[index] = direction_combobox
        
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
        
        self.esc_calibration_entries.append(calib_entries)
        
        power_frame: tk.Frame = tk.Frame(master=section_frame)
        power_frame.pack(fill=tk.X, pady=(10, 5))
        
        power_label: tk.Label = tk.Label(
            master=power_frame, text="Motor Power:", anchor="w"
        )
        power_label.pack(side=tk.LEFT, padx=5)
        
        slider_container: tk.Frame = tk.Frame(master=power_frame)
        slider_container.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        
        power_slider: tk.Scale = tk.Scale(
            master=slider_container,
            from_=-100,
            to=100,
            orient=tk.HORIZONTAL,
            command=lambda val: self._on_power_slider_changed(index, int(val)),
            state="disabled",
        )
        power_slider.set(0)
        power_slider.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        slider_container.bind(
            "<Button-3>", lambda event, idx=index: self._reset_power_slider(idx)
        )
        
        power_value_label: tk.Label = tk.Label(
            master=slider_container,
            text="0.00",
            width=6,
            anchor="center",
            bg="#90EE90",
            fg="black",
            relief=tk.SUNKEN,
            bd=2,
        )
        power_value_label.pack(side=tk.LEFT, padx=5)
        
        power_value_label.bind(
            "<Button-1>", lambda event, idx=index: self._reset_power_slider(idx)
        )
        power_value_label.bind(
            "<Button-2>", lambda event, idx=index: self._reset_power_slider(idx)
        )
        power_value_label.bind(
            "<Button-3>", lambda event, idx=index: self._reset_power_slider(idx)
        )
        
        self.esc_power_sliders.append(power_slider)
        self.esc_power_value_labels.append(power_value_label)
