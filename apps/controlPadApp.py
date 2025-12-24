"""Control Pad application module for directional and rotational controls."""

import tkinter as tk
from typing import Optional, TYPE_CHECKING

from configManager import get_config_manager

if TYPE_CHECKING:
    from .lightControlApp import LightControlApp
    from .escControlApp import ESCControlApp

# Load control scheme from config
config = get_config_manager()


class ControlPadApp:
    """Application for directional and rotational control pad."""

    def __init__(self, parent, light_control_app: Optional["LightControlApp"] = None, esc_control_app: Optional["ESCControlApp"] = None) -> None:
        self.parent = parent
        self.light_control_app = light_control_app
        self.esc_control_app = esc_control_app
        self.window: tk.Toplevel = tk.Toplevel(parent.master)
        self.window.title("Control Pad")
        
        # Dictionary to store custom power levels for each button/action
        self.custom_power_levels: dict[str, list[float]] = {}
        
        self.window.protocol("WM_DELETE_WINDOW", self.on_window_close)
        
        main_frame: tk.Frame = tk.Frame(master=self.window)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=15, pady=15)
        
        # Cluster 1: Movement (Forward, Backward, Left, Right)
        cluster1_frame: tk.LabelFrame = tk.LabelFrame(
            master=main_frame,
            text="Movement",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10,
        )
        cluster1_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        
        # Create 3x3 grid for cluster 1 (but only 5 buttons used, corners disabled)
        movement_grid: tk.Frame = tk.Frame(master=cluster1_frame)
        movement_grid.pack(padx=5, pady=5)
        
        # Row 0: Forward (center only)
        forward_btn = None
        # Define color mapping for buttons
        button_colors = {
            'movement': {'normal': 'lightblue', 'pressed': 'dodgerblue'},
            'stop': {'normal': 'lightcoral', 'pressed': 'red'},
            'rotation': {'normal': 'lightyellow', 'pressed': 'gold'},
            'vertical': {'normal': 'lightgrey', 'pressed': 'green'},
            'light': {'normal': 'lightgray', 'pressed': 'gray'}
        }
        
        for col in range(3):
            if col == 1:
                forward_btn = tk.Button(
                    master=movement_grid,
                    text="Forward",
                    width=12,
                    height=4,
                    bg=button_colors['movement']['normal'],
                    activebackground=button_colors['movement']['pressed'],
                    command=self._esc_forward
                )
                forward_btn.grid(row=0, column=col, padx=2, pady=2)
                forward_btn.bind("<Button-3>", lambda e: self._show_power_editor("forward", forward_btn))
            else:
                spacer = tk.Frame(master=movement_grid, width=12*7, height=4*20)
                spacer.grid(row=0, column=col, padx=2, pady=2)
        
        # Row 1: Rotate Left, Stop, Rotate Right
        left_btn = tk.Button(
            master=movement_grid,
            text="Rotate\nLeft",
            width=12,
            height=4,
            bg=button_colors['movement']['normal'],
            activebackground=button_colors['movement']['pressed'],
            command=self._esc_left
        )
        left_btn.grid(row=1, column=0, padx=2, pady=2)
        left_btn.bind("<Button-3>", lambda e: self._show_power_editor("rotate_left", left_btn))
        
        stop_btn1 = tk.Button(
            master=movement_grid,
            text="Stop",
            width=12,
            height=4,
            bg=button_colors['stop']['normal'],
            activebackground=button_colors['stop']['pressed'],
            command=self._stop_escs
        )
        stop_btn1.grid(row=1, column=1, padx=2, pady=2)
        stop_btn1.bind("<Button-3>", lambda e: self._show_power_editor("stop", stop_btn1))
        
        right_btn = tk.Button(
            master=movement_grid,
            text="Rotate\nRight",
            width=12,
            height=4,
            bg=button_colors['movement']['normal'],
            activebackground=button_colors['movement']['pressed'],
            command=self._esc_right
        )
        right_btn.grid(row=1, column=2, padx=2, pady=2)
        right_btn.bind("<Button-3>", lambda e: self._show_power_editor("rotate_right", right_btn))
        
        # Row 2: Backward (center only)
        backward_btn = None
        for col in range(3):
            if col == 1:
                backward_btn = tk.Button(
                    master=movement_grid,
                    text="Backward",
                    width=12,
                    height=4,
                    bg=button_colors['movement']['normal'],
                    activebackground=button_colors['movement']['pressed'],
                    command=self._esc_backward
                )
                backward_btn.grid(row=2, column=col, padx=2, pady=2)
                backward_btn.bind("<Button-3>", lambda e: self._show_power_editor("backward", backward_btn))
            else:
                spacer = tk.Frame(master=movement_grid, width=12*7, height=4*20)
                spacer.grid(row=2, column=col, padx=2, pady=2)
        
        # Cluster 2: Rotation (Up, Down, Rotate Left, Rotate Right)
        cluster2_frame: tk.LabelFrame = tk.LabelFrame(
            master=main_frame,
            text="Rotation",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10,
        )
        cluster2_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        
        # Create 3x3 grid for cluster 2
        rotation_grid: tk.Frame = tk.Frame(master=cluster2_frame)
        rotation_grid.pack(padx=5, pady=5)
        
        # Row 0: X, Up, X
        up_btn = None
        for col in range(3):
            if col == 1:
                up_btn = tk.Button(
                    master=rotation_grid,
                    text="Up",
                    width=12,
                    height=4,
                    bg=button_colors['vertical']['normal'],
                    activebackground=button_colors['vertical']['pressed'],
                    command=self._esc_up
                )
                up_btn.grid(row=0, column=col, padx=2, pady=2)
                up_btn.bind("<Button-3>", lambda e: self._show_power_editor("up", up_btn))
            else:
                spacer = tk.Frame(master=rotation_grid, width=12*7, height=4*20)
                spacer.grid(row=0, column=col, padx=2, pady=2)
        
        # Row 1: Rotate Left, Stop, Rotate Right
        rotate_left_btn = tk.Button(
            master=rotation_grid,
            text="Roll\nLeft",
            width=12,
            height=4,
            bg=button_colors['rotation']['normal'],
            activebackground=button_colors['rotation']['pressed'],
            command=self._esc_roll_left
        )
        rotate_left_btn.grid(row=1, column=0, padx=2, pady=2)
        rotate_left_btn.bind("<Button-3>", lambda e: self._show_power_editor("roll_left", rotate_left_btn))
        
        stop_btn2 = tk.Button(
            master=rotation_grid,
            text="Stop",
            width=12,
            height=4,
            bg=button_colors['stop']['normal'],
            activebackground=button_colors['stop']['pressed'],
            command=self._stop_escs
        )
        stop_btn2.grid(row=1, column=1, padx=2, pady=2)
        stop_btn2.bind("<Button-3>", lambda e: self._show_power_editor("stop", stop_btn2))
        
        rotate_right_btn = tk.Button(
            master=rotation_grid,
            text="Roll\nRight",
            width=12,
            height=4,
            bg=button_colors['rotation']['normal'],
            activebackground=button_colors['rotation']['pressed'],
            command=self._esc_roll_right
        )
        rotate_right_btn.grid(row=1, column=2, padx=2, pady=2)
        rotate_right_btn.bind("<Button-3>", lambda e: self._show_power_editor("roll_right", rotate_right_btn))
        
        # Row 2: X, Down, X
        down_btn = None
        for col in range(3):
            if col == 1:
                down_btn = tk.Button(
                    master=rotation_grid,
                    text="Down",
                    width=12,
                    height=4,
                    bg=button_colors['vertical']['normal'],
                    activebackground=button_colors['vertical']['pressed'],
                    command=self._esc_down
                )
                down_btn.grid(row=2, column=col, padx=2, pady=2)
                down_btn.bind("<Button-3>", lambda e: self._show_power_editor("down", down_btn))
            else:
                spacer = tk.Frame(master=rotation_grid, width=12*7, height=4*20)
                spacer.grid(row=2, column=col, padx=2, pady=2)
        
        # Cluster 3: Light Control
        cluster3_frame: tk.LabelFrame = tk.LabelFrame(
            master=main_frame,
            text="Light",
            font=("Arial", 10, "bold"),
            padx=10,
            pady=10,
        )
        cluster3_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10)
        
        # Create vertical stack for cluster 3
        light_grid: tk.Frame = tk.Frame(master=cluster3_frame)
        light_grid.pack(padx=5, pady=5)
        
        # +Light button
        light_up_btn = tk.Button(
            master=light_grid,
            text="+Light",
            width=10,
            height=3,
            bg=button_colors['light']['normal'],
            activebackground=button_colors['light']['pressed'],
            command=self._increase_light
        )
        light_up_btn.grid(row=0, column=0, padx=2, pady=2)
        
        # -Light button
        light_down_btn = tk.Button(
            master=light_grid,
            text="-Light",
            width=10,
            height=3,
            bg=button_colors['light']['normal'],
            activebackground=button_colors['light']['pressed'],
            command=self._decrease_light
        )
        light_down_btn.grid(row=1, column=0, padx=2, pady=2)
        
        # Auto-size window to fit content
        self.window.update_idletasks()
        width = main_frame.winfo_reqwidth() + 30
        height = main_frame.winfo_reqheight() + 30
        self.window.geometry(f"{width}x{height}")
        
        # Focus on window to enable key bindings
        self.window.focus_set()
        
        # Create a dictionary to track pressed states and original colors
        pressed_states = {}
        
        # Helper function to get button color type
        def get_button_color_type(btn) -> str:
            """Determine which color type a button belongs to."""
            if btn in [forward_btn, left_btn, right_btn, backward_btn]:
                return 'movement'
            elif btn in [stop_btn1, stop_btn2]:
                return 'stop'
            elif btn in [rotate_left_btn, rotate_right_btn]:
                return 'rotation'
            elif btn in [up_btn, down_btn]:
                return 'vertical'
            elif btn in [light_up_btn, light_down_btn]:
                return 'light'
            return 'movement'
        
        # Helper function to handle key press
        def on_key_press(button, key: str) -> None:
            """Handle key press - show button as pressed."""
            if key not in pressed_states:
                pressed_states[key] = False
            
            if not pressed_states[key]:
                pressed_states[key] = True
                if button:
                    color_type = get_button_color_type(button)
                    button.config(relief=tk.SUNKEN, bg=button_colors[color_type]['pressed'])
        
        # Helper function to handle key release
        def on_key_release(button, key: str) -> None:
            """Handle key release - release button and invoke command."""
            if key in pressed_states and pressed_states[key]:
                pressed_states[key] = False
                if button:
                    color_type = get_button_color_type(button)
                    button.config(relief=tk.RAISED, bg=button_colors[color_type]['normal'])
                    button.invoke()
        
        # Bind keys for keyboard control - use KeyPress and KeyRelease
        self.window.bind(f'<KeyPress-w>', lambda e: on_key_press(forward_btn, 'w'))
        self.window.bind(f'<KeyRelease-w>', lambda e: on_key_release(forward_btn, 'w'))
        
        self.window.bind(f'<KeyPress-s>', lambda e: on_key_press(backward_btn, 's'))
        self.window.bind(f'<KeyRelease-s>', lambda e: on_key_release(backward_btn, 's'))
        
        self.window.bind(f'<KeyPress-a>', lambda e: on_key_press(left_btn, 'a'))
        self.window.bind(f'<KeyRelease-a>', lambda e: on_key_release(left_btn, 'a'))
        
        self.window.bind(f'<KeyPress-d>', lambda e: on_key_press(right_btn, 'd'))
        self.window.bind(f'<KeyRelease-d>', lambda e: on_key_release(right_btn, 'd'))
        
        self.window.bind(f'<KeyPress-u>', lambda e: on_key_press(up_btn, 'u'))
        self.window.bind(f'<KeyRelease-u>', lambda e: on_key_release(up_btn, 'u'))
        
        self.window.bind(f'<KeyPress-j>', lambda e: on_key_press(down_btn, 'j'))
        self.window.bind(f'<KeyRelease-j>', lambda e: on_key_release(down_btn, 'j'))
        
        self.window.bind(f'<KeyPress-i>', lambda e: on_key_press(rotate_left_btn, 'i'))
        self.window.bind(f'<KeyRelease-i>', lambda e: on_key_release(rotate_left_btn, 'i'))
        
        self.window.bind(f'<KeyPress-k>', lambda e: on_key_press(rotate_right_btn, 'k'))
        self.window.bind(f'<KeyRelease-k>', lambda e: on_key_release(rotate_right_btn, 'k'))
        
        self.window.bind(f'<KeyPress-o>', lambda e: on_key_press(light_up_btn, 'o'))
        self.window.bind(f'<KeyRelease-o>', lambda e: on_key_release(light_up_btn, 'o'))
        
        self.window.bind(f'<KeyPress-l>', lambda e: on_key_press(light_down_btn, 'l'))
        self.window.bind(f'<KeyRelease-l>', lambda e: on_key_release(light_down_btn, 'l'))
        
        # Special binding for 'x' - stop (affects both stop buttons)
        def on_stop_press() -> None:
            """Handle stop key press - press both stop buttons."""
            if 'x' not in pressed_states:
                pressed_states['x'] = False
            
            if not pressed_states['x']:
                pressed_states['x'] = True
                stop_btn1.config(relief=tk.SUNKEN, bg=button_colors['stop']['pressed'])
                stop_btn2.config(relief=tk.SUNKEN, bg=button_colors['stop']['pressed'])
        
        def on_stop_release() -> None:
            """Handle stop key release - release both stop buttons."""
            if 'x' in pressed_states and pressed_states['x']:
                pressed_states['x'] = False
                stop_btn1.config(relief=tk.RAISED, bg=button_colors['stop']['normal'])
                stop_btn2.config(relief=tk.RAISED, bg=button_colors['stop']['normal'])
                stop_btn1.invoke()
                stop_btn2.invoke()
        
        self.window.bind(f'<KeyPress-x>', lambda e: on_stop_press())
        self.window.bind(f'<KeyRelease-x>', lambda e: on_stop_release())
        
        self.update_connection_state()

    def update_connection_state(self) -> None:
        """Update UI based on connection state."""
        # Placeholder for future connection state updates
        pass

    def set_light_control_app(self, light_control_app: Optional["LightControlApp"]) -> None:
        """Update the reference to light control app."""
        self.light_control_app = light_control_app

    def set_esc_control_app(self, esc_control_app: Optional["ESCControlApp"]) -> None:
        """Update the reference to ESC control app."""
        self.esc_control_app = esc_control_app

    def _increase_light(self) -> None:
        """Increase light power level."""
        if self.light_control_app:
            self.light_control_app.increase_power()

    def _decrease_light(self) -> None:
        """Decrease light power level."""
        if self.light_control_app:
            self.light_control_app.decrease_power()

    def _esc_forward(self) -> None:
        """Forward movement with power levels from config or custom."""
        if self.esc_control_app:
            power_levels = self.custom_power_levels.get("forward") or config.get("control_pad.forward", [-0.15, 0.15, 0.0, 0.10])
            self.esc_control_app.send_all_esc_power(power_levels)

    def _esc_backward(self) -> None:
        """Backward movement with power levels from config or custom."""
        if self.esc_control_app:
            power_levels = self.custom_power_levels.get("backward") or config.get("control_pad.backward", [0.20, -0.20, 0.0, -0.15])
            self.esc_control_app.send_all_esc_power(power_levels)

    def _esc_left(self) -> None:
        """Turn left (rotate left) with power levels from config or custom."""
        if self.esc_control_app:
            power_levels = self.custom_power_levels.get("rotate_left") or config.get("control_pad.rotate_left", [0.0, 0.0, -0.15, -0.03])
            self.esc_control_app.send_all_esc_power(power_levels)

    def _esc_right(self) -> None:
        """Turn right (rotate right) with power levels from config or custom."""
        if self.esc_control_app:
            power_levels = self.custom_power_levels.get("rotate_right") or config.get("control_pad.rotate_right", [0.0, 0.0, 0.50, -0.03])
            self.esc_control_app.send_all_esc_power(power_levels)

    def _esc_up(self) -> None:
        """Ascend with power levels from config or custom."""
        if self.esc_control_app:
            power_levels = self.custom_power_levels.get("up") or config.get("control_pad.up", [0.25, 0.25, 0.0, 0.0])
            self.esc_control_app.send_all_esc_power(power_levels)

    def _esc_down(self) -> None:
        """Descend with power levels from config or custom."""
        if self.esc_control_app:
            power_levels = self.custom_power_levels.get("down") or config.get("control_pad.down", [-0.15, -0.15, 0.0, 0.0])
            self.esc_control_app.send_all_esc_power(power_levels)

    def _esc_roll_left(self) -> None:
        """Roll left with power levels from config or custom."""
        if self.esc_control_app:
            power_levels = self.custom_power_levels.get("roll_left") or config.get("control_pad.roll_left", [0.75, -0.3, 0.0, 0.0])
            self.esc_control_app.send_all_esc_power(power_levels)

    def _esc_roll_right(self) -> None:
        """Roll right with power levels from config or custom."""
        if self.esc_control_app:
            power_levels = self.custom_power_levels.get("roll_right") or config.get("control_pad.roll_right", [-0.425, 0.6, 0.0, 0.0])
            self.esc_control_app.send_all_esc_power(power_levels)

    def _stop_escs(self) -> None:
        """Stop all ESCs by setting power to 0.00."""
        if self.esc_control_app:
            power_levels = self.custom_power_levels.get("stop") or config.get("control_pad.stop", [0.0] * self.esc_control_app.num_escs)
            self.esc_control_app.send_all_esc_power(power_levels)

    def on_window_close(self) -> None:
        """Handle window close event."""
        self._save_custom_power_levels()
        self.window.withdraw()
    
    def _save_custom_power_levels(self) -> None:
        """Save custom power levels to config."""
        try:
            for action, levels in self.custom_power_levels.items():
                config.set(f"control_pad.{action}", levels)
            config.save()
        except Exception as e:
            print(f"Error saving custom power levels: {e}")
    
    def _show_power_editor(self, action: str, button: Optional[tk.Button]) -> None:
        """Show a popup to edit individual ESC power levels for an action."""
        # Get the number of ESCs from esc_control_app
        if not self.esc_control_app or not button:
            return
        
        num_escs = self.esc_control_app.num_escs
        
        # Get current power levels (from custom or config defaults)
        if action in self.custom_power_levels:
            current_levels = self.custom_power_levels[action].copy()
        else:
            current_levels = config.get(f"control_pad.{action}", [0.0] * num_escs)
        
        # Ensure we have the right number of levels
        while len(current_levels) < num_escs:
            current_levels.append(0.0)
        current_levels = current_levels[:num_escs]
        
        # Create popup window
        popup = tk.Toplevel(self.window)
        popup.title(f"Edit {action.replace('_', ' ').title()} Power Levels")
        popup.resizable(False, False)
        
        # Create frame for sliders
        frame = tk.Frame(popup, padx=10, pady=10)
        frame.pack(fill=tk.BOTH, expand=True)
        
        # Store slider values
        slider_vars: list[tk.DoubleVar] = []
        sliders: list[tk.Scale] = []
        
        # Create sliders for each ESC
        title_label = tk.Label(frame, text=f"ESC Power Levels (-1.0 to 1.0)", font=("Arial", 10, "bold"))
        title_label.pack(pady=5)
        
        for i in range(num_escs):
            esc_id = i + 1
            row_frame = tk.Frame(frame)
            row_frame.pack(fill=tk.X, pady=5)
            
            label = tk.Label(row_frame, text=f"ESC {esc_id}:", width=10)
            label.pack(side=tk.LEFT, padx=5)
            
            var = tk.DoubleVar(value=current_levels[i])
            slider_vars.append(var)
            
            slider = tk.Scale(
                row_frame,
                from_=-1.0,
                to=1.0,
                resolution=0.05,
                orient=tk.HORIZONTAL,
                variable=var,
                width=20,
                length=200
            )
            slider.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
            sliders.append(slider)
            
            # Display current value
            value_label = tk.Label(row_frame, text=f"{current_levels[i]:.2f}", width=6)
            value_label.pack(side=tk.LEFT, padx=5)
            
            # Update value label when slider changes
            def update_label(val, lbl=value_label, var=var):
                lbl.config(text=f"{var.get():.2f}")
            
            var.trace("w", update_label)
        
        # Button frame
        button_frame = tk.Frame(frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        def save_and_close():
            """Save the power levels and close the popup."""
            levels = [var.get() for var in slider_vars]
            self.custom_power_levels[action] = levels
            self._save_custom_power_levels()
            popup.destroy()
        
        def close_popup():
            """Close without saving."""
            popup.destroy()
        
        save_btn = tk.Button(button_frame, text="Save", command=save_and_close, width=10)
        save_btn.pack(side=tk.LEFT, padx=5)
        
        cancel_btn = tk.Button(button_frame, text="Cancel", command=close_popup, width=10)
        cancel_btn.pack(side=tk.LEFT, padx=5)
        
        # Close on click outside
        def on_focus_out(e):
            if e.widget == popup:
                popup.destroy()
        
        popup.bind("<FocusOut>", on_focus_out)
        
        # Position popup near the button
        self.window.update_idletasks()
        x = button.winfo_rootx() + button.winfo_width() // 2 - 200
        y = button.winfo_rooty() + button.winfo_height() // 2 - 150
        popup.geometry(f"+{x}+{y}")
        
        popup.focus_set()
