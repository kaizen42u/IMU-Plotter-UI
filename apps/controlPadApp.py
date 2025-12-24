"""Control Pad application module for directional and rotational controls."""

import tkinter as tk
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .lightControlApp import LightControlApp


class ControlPadApp:
    """Application for directional and rotational control pad."""

    def __init__(self, parent, light_control_app: Optional["LightControlApp"] = None) -> None:
        self.parent = parent
        self.light_control_app = light_control_app
        self.window: tk.Toplevel = tk.Toplevel(parent.master)
        self.window.title("Control Pad")
        
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
                    activebackground=button_colors['movement']['pressed']
                )
                forward_btn.grid(row=0, column=col, padx=2, pady=2)
            else:
                spacer = tk.Frame(master=movement_grid, width=12*7, height=4*20)
                spacer.grid(row=0, column=col, padx=2, pady=2)
        
        # Row 1: Left, Stop, Right
        left_btn = tk.Button(
            master=movement_grid,
            text="Left",
            width=12,
            height=4,
            bg=button_colors['movement']['normal'],
            activebackground=button_colors['movement']['pressed']
        )
        left_btn.grid(row=1, column=0, padx=2, pady=2)
        
        stop_btn1 = tk.Button(
            master=movement_grid,
            text="Stop",
            width=12,
            height=4,
            bg=button_colors['stop']['normal'],
            activebackground=button_colors['stop']['pressed']
        )
        stop_btn1.grid(row=1, column=1, padx=2, pady=2)
        
        right_btn = tk.Button(
            master=movement_grid,
            text="Right",
            width=12,
            height=4,
            bg=button_colors['movement']['normal'],
            activebackground=button_colors['movement']['pressed']
        )
        right_btn.grid(row=1, column=2, padx=2, pady=2)
        
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
                    activebackground=button_colors['movement']['pressed']
                )
                backward_btn.grid(row=2, column=col, padx=2, pady=2)
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
                    activebackground=button_colors['vertical']['pressed']
                )
                up_btn.grid(row=0, column=col, padx=2, pady=2)
            else:
                spacer = tk.Frame(master=rotation_grid, width=12*7, height=4*20)
                spacer.grid(row=0, column=col, padx=2, pady=2)
        
        # Row 1: Rotate Left, Stop, Rotate Right
        rotate_left_btn = tk.Button(
            master=rotation_grid,
            text="Rotate\nLeft",
            width=12,
            height=4,
            bg=button_colors['rotation']['normal'],
            activebackground=button_colors['rotation']['pressed']
        )
        rotate_left_btn.grid(row=1, column=0, padx=2, pady=2)
        
        stop_btn2 = tk.Button(
            master=rotation_grid,
            text="Stop",
            width=12,
            height=4,
            bg=button_colors['stop']['normal'],
            activebackground=button_colors['stop']['pressed']
        )
        stop_btn2.grid(row=1, column=1, padx=2, pady=2)
        
        rotate_right_btn = tk.Button(
            master=rotation_grid,
            text="Rotate\nRight",
            width=12,
            height=4,
            bg=button_colors['rotation']['normal'],
            activebackground=button_colors['rotation']['pressed']
        )
        rotate_right_btn.grid(row=1, column=2, padx=2, pady=2)
        
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
                    activebackground=button_colors['vertical']['pressed']
                )
                down_btn.grid(row=2, column=col, padx=2, pady=2)
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

    def _increase_light(self) -> None:
        """Increase light power level."""
        if self.light_control_app:
            self.light_control_app.increase_power()

    def _decrease_light(self) -> None:
        """Decrease light power level."""
        if self.light_control_app:
            self.light_control_app.decrease_power()

    def on_window_close(self) -> None:
        """Handle window close event."""
        self.window.withdraw()
