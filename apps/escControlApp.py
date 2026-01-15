"""ESC Control application module."""

import threading
import tkinter as tk
from tkinter import ttk
from typing import cast, TYPE_CHECKING

from configManager import get_config_manager
from tkGPIOCombobox import tkGPIOCombobox
from esp32_hw import GPIO

if TYPE_CHECKING:
    from .serialTerminal import SerialTerminal

# Load ESC configuration from config
config = get_config_manager()


class ESCControlApp:
    """Application for controlling Electronic Speed Controllers."""

    FREQUENCY_OPTIONS: list[str] = ["50Hz", "100Hz", "200Hz", "300Hz"]
    DIRECTION_OPTIONS: list[str] = ["Normal", "Inverted"]

    def __init__(self, parent: tk.Tk | tk.Frame, serial_terminal: "SerialTerminal") -> None:
        self.parent = parent
        self.serial_terminal = serial_terminal
        self.window: tk.Toplevel = tk.Toplevel(parent)
        self.window.title("ESC Control")

        self.window.protocol("WM_DELETE_WINDOW", self.on_window_close)

        # Register connection state callback
        self.serial_terminal.register_connection_state_callback(
            self._on_connection_state_changed
        )

        # Load number of ESCs from config or use default
        self.num_escs: int = config.get("esc.num_of_esc", 4)

        # Load ESC configs from config file or use defaults
        self.esc_configs: list[dict[str, str | list[int]]] = []
        for i in range(1, self.num_escs + 1):
            esc_cfg = config.get(f"esc.esc{i}")
            if esc_cfg:
                self.esc_configs.append(esc_cfg)
            else:
                # Create a default config for each ESC
                self.esc_configs.append(
                    {
                        "gpio": f"{8 + i}",
                        "direction": "Normal",
                        "calibration": [1000, 1500, 1500, 1500, 2000],
                    }
                )

        # Load ESC frequency from config
        self.esc_frequency = config.get("esc.frequency", "300Hz")

        # Initialize lists based on number of ESCs
        self.esc_gpio_comboboxes: list[tkGPIOCombobox | None] = [None] * self.num_escs
        self.esc_direction_comboboxes: list[ttk.Combobox | None] = [
            None
        ] * self.num_escs
        self.esc_initialized: list[bool] = [False] * self.num_escs
        self.esc_selected: list[tk.BooleanVar] = [
            tk.BooleanVar(value=True) for _ in range(self.num_escs)
        ]
        self.esc_calibration_entries: list[list[tk.Entry]] = []
        self.esc_power_sliders: list[tk.Scale] = []
        self.esc_power_value_labels: list[tk.Label] = []

        self.esc_power_pending: list[float | None] = [None] * self.num_escs
        self.esc_power_send_scheduled: list[bool] = [False] * self.num_escs

        # Background thread for ESC power level monitoring
        self.esc_power_monitor_thread: threading.Thread | None = None
        self.esc_power_monitor_active: bool = True
        self.esc_current_power_levels: list[float] = [0.0] * self.num_escs
        self.esc_last_sent_power_levels: list[float] = [-1.0] * self.num_escs
        self.esc_power_lock = threading.Lock()

        # Create canvas with scrollbar for scrollable content
        canvas = tk.Canvas(master=self.window, bg="white")
        scrollbar = tk.Scrollbar(
            master=self.window, orient=tk.VERTICAL, command=canvas.yview
        )

        main_frame: tk.Frame = tk.Frame(master=canvas)
        main_frame.bind(
            "<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )

        canvas.create_window((0, 0), window=main_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # Pack canvas and scrollbar
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Bind mousewheel scrolling
        def on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", on_mousewheel)

        self._create_common_section(main_frame)

        for esc_id in range(1, self.num_escs + 1):
            self._create_esc_section(main_frame, esc_id - 1, esc_id)

        # Auto-size window to fit content
        self.window.update_idletasks()
        width = min(main_frame.winfo_reqwidth() + 40, 900)  # Cap width at 900px
        height = min(main_frame.winfo_reqheight() + 40, 700)  # Cap height at 700px
        self.window.geometry(f"{width}x{height}")

        # Start background power monitor thread
        self._start_power_monitor_thread()

    def _on_connection_state_changed(self) -> None:
        """Callback when connection state changes."""
        if self.window.winfo_exists():
            self.update_connection_state()

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
        self.frequency_combobox.set(self.esc_frequency)
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
        """Hide window instead of closing it and save config."""
        # Save current ESC configurations to config file
        self._save_esc_config()

        # Stop the background monitor thread when window closes
        self.esc_power_monitor_active = False
        if self.esc_power_monitor_thread is not None:
            self.esc_power_monitor_thread.join(timeout=1)
        self.window.withdraw()

    def _save_esc_config(self) -> None:
        """Save current ESC configurations to config file."""
        try:
            # Save frequency
            frequency = self.frequency_combobox.get()
            config.set("esc.frequency", frequency)

            # Save number of ESCs
            config.set("esc.num_of_esc", self.num_escs)

            for index in range(self.num_escs):
                esc_id = index + 1

                # Get current values from UI
                if self.esc_gpio_comboboxes[index] is not None:
                    gpio_box = cast(tkGPIOCombobox, self.esc_gpio_comboboxes[index])
                    gpio = gpio_box.get()
                else:
                    gpio = self.esc_configs[index].get("gpio", f"{9 + index}")

                if self.esc_direction_comboboxes[index] is not None:
                    direction = cast(
                        ttk.Combobox, self.esc_direction_comboboxes[index]
                    ).get()
                else:
                    direction = self.esc_configs[index].get("direction", "Normal")

                if hasattr(self, "esc_calibration_entries") and index < len(
                    self.esc_calibration_entries
                ):
                    try:
                        calibration = [
                            int(entry.get())
                            for entry in self.esc_calibration_entries[index]
                        ]
                    except ValueError:
                        calibration = self.esc_configs[index].get(
                            "calibration", [1000, 1500, 1500, 1500, 2000]
                        )
                else:
                    calibration = self.esc_configs[index].get(
                        "calibration", [1000, 1500, 1500, 1500, 2000]
                    )

                # Update config
                config.set(f"esc.esc{esc_id}.gpio", gpio)
                config.set(f"esc.esc{esc_id}.direction", direction)
                config.set(f"esc.esc{esc_id}.calibration", calibration)

            # Save config to file
            config.save()
        except Exception as e:
            print(f"Error saving ESC config: {e}")

    def init_escs(self) -> None:
        """Send init commands for enabled ESCs."""
        command_delay = 0

        for index in range(self.num_escs):
            esc_id = index + 1

            if not self.esc_selected[index].get():
                continue

            if self.esc_initialized[index]:
                continue

            if self.esc_gpio_comboboxes[index] is None:
                continue

            direction_combobox: ttk.Combobox = cast(
                ttk.Combobox, self.esc_direction_comboboxes[index]
            )
            gpio_combobox: tkGPIOCombobox = cast(
                tkGPIOCombobox, self.esc_gpio_comboboxes[index]
            )
            gpio = gpio_combobox.get()
            gpio_str = str(gpio) if gpio else ""
            direction_str: str = direction_combobox.get()
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
                calib_values = self.esc_configs[index].get(
                    "calibration", [1000, 1500, 1500, 1500, 2000]
                )

            freq_str: str = self.frequency_combobox.get()
            freq_num = freq_str.replace("Hz", "")
            freq_command = f"esc freq {freq_num}"
            self.window.after(
                command_delay, lambda cmd=freq_command: self._send_command(cmd)
            )
            command_delay += 200

            init_command = f"esc {esc_id} init {gpio_str}"
            self.window.after(
                command_delay,
                lambda cmd=init_command, idx=index: self._send_init_command(cmd, idx),
            )
            command_delay += 200

            dir_command = f"esc {esc_id} dir {direction_num}"
            self.window.after(
                command_delay, lambda cmd=dir_command: self._send_command(cmd)
            )
            command_delay += 200

            cali_command = f"esc {esc_id} cali {calib_values[0]} {calib_values[1]} {calib_values[2]} {calib_values[3]} {calib_values[4]}"
            self.window.after(
                command_delay,
                lambda cmd=cali_command: self._send_command(cmd),
            )
            command_delay += 200

            power_sequence = [0.00, -0.01, 0.00, 0.01, 0.00]
            for power_val in power_sequence:
                pw_command = f"esc {esc_id} pw {power_val:.2f}"
                self.window.after(
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

        for index in range(self.num_escs):
            esc_id = index + 1

            if not self.esc_selected[index].get():
                continue

            if not self.esc_initialized[index]:
                continue

            deinit_command = f"esc {esc_id} deinit"
            self.window.after(
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
            gpio_box: tkGPIOCombobox = cast(tkGPIOCombobox, self.esc_gpio_comboboxes[index])
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
        is_connected = self.serial_terminal.serial.is_connected()

        selected_indices = [
            i for i in range(self.num_escs) if self.esc_selected[i].get()
        ]

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
        """Handle power slider change - update the monitor thread."""
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

        # Update the power level for the background monitor thread
        with self.esc_power_lock:
            self.esc_current_power_levels[index] = power

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

            if self.serial_terminal.serial.is_connected():
                self.serial_terminal.send_command(command)
            else:
                print("Serial port is not connected")
        except Exception as e:
            print(f"Error sending command: {e}")

    def send_all_esc_power(self, power_levels: list[float]) -> None:
        """Send power commands for all ESCs (only if different from last sent values)."""
        # Truncate power_levels to match the configured number of ESCs
        power_levels = power_levels[: self.num_escs]

        if len(power_levels) < self.num_escs:
            print(
                f"Warning: Expected {self.num_escs} power levels, got {len(power_levels)}"
            )

        with self.esc_power_lock:
            for esc_index in range(self.num_escs):
                # Only send if power level changed and ESC is initialized
                if (
                    power_levels[esc_index]
                    != self.esc_last_sent_power_levels[esc_index]
                    and self.esc_initialized[esc_index]
                ):
                    power = power_levels[esc_index]
                    esc_id = esc_index + 1
                    command = f"esc {esc_id} pw {power:.2f}"
                    threading.Thread(
                        target=self._send_command, args=(command,), daemon=True
                    ).start()
                    # Update both last_sent and current to keep them in sync
                    self.esc_last_sent_power_levels[esc_index] = power
                    self.esc_current_power_levels[esc_index] = power

        # Update UI sliders to reflect the new power levels
        self._update_power_sliders()

    def stop_all_escs(self) -> None:
        """Stop all ESCs by setting power to 0.00."""
        # Create stop command for all configured ESCs
        stop_levels = [0.0] * self.num_escs
        self.send_all_esc_power(stop_levels)
        self._update_power_sliders()

    def _update_power_sliders(self) -> None:
        """Update all power sliders to reflect current power levels."""
        if hasattr(self, "esc_power_sliders") and self.window.winfo_exists():
            with self.esc_power_lock:
                # Make a copy to avoid holding lock during UI update
                current_levels = self.esc_current_power_levels.copy()

            for index in range(self.num_escs):
                if index < len(self.esc_power_sliders):
                    # Convert to slider scale (0-100)
                    slider_value = int(current_levels[index] * 100)
                    self.esc_power_sliders[index].set(slider_value)

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

        gpio_combobox: tkGPIOCombobox = tkGPIOCombobox(
            master=gpio_frame,
            width=12,
        )
        gpio = self.esc_configs[index].get("gpio", f"GPIO{9 + index}")
        if isinstance(gpio, str):
            gpio_combobox.set(gpio)
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
        direction_combobox.set(self.esc_configs[index].get("direction", "Normal"))
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
        default_calib: list[int] = self.esc_configs[index].get("calibration", [1000, 1500, 1500, 1500, 2000])  # type: ignore

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

    def _start_power_monitor_thread(self) -> None:
        """Start the background thread that monitors and sends power level changes."""
        self.esc_power_monitor_thread = threading.Thread(
            target=self._esc_power_monitor_loop, daemon=True
        )
        self.esc_power_monitor_thread.start()

    def _esc_power_monitor_loop(self) -> None:
        """Background thread loop that monitors power level changes and sends commands."""
        import time

        while self.esc_power_monitor_active:
            try:
                with self.esc_power_lock:
                    current_levels = self.esc_current_power_levels.copy()
                    last_sent_levels = self.esc_last_sent_power_levels.copy()

                # Send command for each ESC if power level changed and ESC is initialized
                for esc_index in range(self.num_escs):
                    if (
                        current_levels[esc_index] != last_sent_levels[esc_index]
                        and self.esc_initialized[esc_index]
                    ):
                        power = current_levels[esc_index]
                        esc_id = esc_index + 1
                        command = f"esc {esc_id} pw {power:.2f}"
                        self._send_command(command)

                        with self.esc_power_lock:
                            self.esc_last_sent_power_levels[esc_index] = power

                # Small sleep to avoid busy waiting
                time.sleep(0.05)
            except Exception as e:
                print(f"Error in ESC power monitor thread: {e}")
