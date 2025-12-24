"""Main entry point for IMU Plotter UI application."""

import tkinter as tk
from typing import Optional

from apps.serialTerminal import SerialTerminal
from apps.imuPlotter import IMUPlotter
from apps.escControlApp import ESCControlApp
from apps.lightControlApp import LightControlApp
from apps.controlPadApp import ControlPadApp


# Global references for control apps
esc_control_app: Optional[ESCControlApp] = None
light_control_app: Optional[LightControlApp] = None
control_pad_app: Optional[ControlPadApp] = None
imu_plotter_window: Optional[tk.Toplevel] = None
imu_plotter_app: Optional[IMUPlotter] = None


def create_serial_wrapper(serial_terminal: SerialTerminal):
    """Create a wrapper object with serial attribute for compatibility with control apps."""
    class SerialWrapper:
        def __init__(self, serial_terminal):
            self.serial = serial_terminal.serial
            self.master = serial_terminal.master
            self._async_log_and_display = serial_terminal._async_log_and_display
    
    return SerialWrapper(serial_terminal)


def toggle_esc_control(serial_terminal: SerialTerminal):
    """Toggle ESC control window visibility."""
    global esc_control_app, control_pad_app
    
    if esc_control_app is None or not esc_control_app.window.winfo_exists():
        wrapper = create_serial_wrapper(serial_terminal)
        esc_control_app = ESCControlApp(parent=wrapper)
        
        # Update control pad's reference to esc_control_app
        if control_pad_app is not None:
            control_pad_app.set_esc_control_app(esc_control_app)
        
        # Handle window close - just hide it instead of destroying
        def on_esc_window_close():
            if esc_control_app is not None:
                esc_control_app.window.withdraw()
        
        esc_control_app.window.protocol("WM_DELETE_WINDOW", on_esc_window_close)
    else:
        # Toggle visibility - always update control pad reference
        if control_pad_app is not None:
            control_pad_app.set_esc_control_app(esc_control_app)
        
        if esc_control_app.window.winfo_viewable():
            esc_control_app.window.withdraw()
        else:
            esc_control_app.window.deiconify()
            esc_control_app.window.lift()


def toggle_light_control(serial_terminal: SerialTerminal):
    """Toggle light control window visibility."""
    global light_control_app, control_pad_app
    
    if light_control_app is None or not light_control_app.window.winfo_exists():
        wrapper = create_serial_wrapper(serial_terminal)
        light_control_app = LightControlApp(parent=wrapper)
        
        # Update control pad's reference to light_control_app
        if control_pad_app is not None:
            control_pad_app.set_light_control_app(light_control_app)
        
        # Handle window close - just hide it instead of destroying
        def on_light_window_close():
            if light_control_app is not None:
                light_control_app.window.withdraw()
        
        light_control_app.window.protocol("WM_DELETE_WINDOW", on_light_window_close)
    else:
        # Toggle visibility - always update control pad reference
        if control_pad_app is not None:
            control_pad_app.set_light_control_app(light_control_app)
        
        if light_control_app.window.winfo_viewable():
            light_control_app.window.withdraw()
        else:
            light_control_app.window.deiconify()
            light_control_app.window.lift()


def toggle_control_pad(serial_terminal: SerialTerminal):
    """Toggle control pad window visibility."""
    global control_pad_app, light_control_app, esc_control_app
    
    if control_pad_app is None or not control_pad_app.window.winfo_exists():
        wrapper = create_serial_wrapper(serial_terminal)
        control_pad_app = ControlPadApp(parent=wrapper, light_control_app=light_control_app, esc_control_app=esc_control_app)
        
        # Handle window close - just hide it instead of destroying
        def on_control_pad_window_close():
            if control_pad_app is not None:
                control_pad_app.window.withdraw()
        
        control_pad_app.window.protocol("WM_DELETE_WINDOW", on_control_pad_window_close)
    else:
        # Update references in case control apps were created after control_pad
        control_pad_app.set_light_control_app(light_control_app)
        control_pad_app.set_esc_control_app(esc_control_app)
        # Toggle visibility
        if control_pad_app.window.winfo_viewable():
            control_pad_app.window.withdraw()
        else:
            control_pad_app.window.deiconify()
            control_pad_app.window.lift()


def toggle_imu_plotter(serial_terminal: SerialTerminal):
    """Toggle IMU plotter window visibility."""
    global imu_plotter_window, imu_plotter_app
    
    if imu_plotter_window is None or not imu_plotter_window.winfo_exists():
        # Create new IMU plotter window
        imu_plotter_window = tk.Toplevel()
        imu_plotter_window.title("IMU Plotter")
        
        # Create frame for IMU plotter
        imu_frame = tk.Frame(master=imu_plotter_window)
        imu_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create IMU plotter in the new window
        imu_plotter_app = IMUPlotter(master=imu_frame, serial_terminal=serial_terminal)
        
        # Auto-size window to fit content
        imu_plotter_window.update_idletasks()
        width = imu_frame.winfo_reqwidth() + 10
        height = imu_frame.winfo_reqheight() + 10
        imu_plotter_window.geometry(f"{width}x{height}")
        
        # Handle window close - just hide it instead of destroying
        def on_imu_window_close():
            if imu_plotter_window is not None:
                imu_plotter_window.withdraw()
        
        imu_plotter_window.protocol("WM_DELETE_WINDOW", on_imu_window_close)
    else:
        # Toggle visibility
        if imu_plotter_window is not None:
            if imu_plotter_window.winfo_viewable():
                imu_plotter_window.withdraw()
            else:
                imu_plotter_window.deiconify()
                imu_plotter_window.lift()


def update_control_apps_state():
    """Update control apps when connection state changes."""
    if esc_control_app and esc_control_app.window.winfo_exists():
        esc_control_app.update_connection_state()
    if light_control_app and light_control_app.window.winfo_exists():
        light_control_app.update_connection_state()


def on_closing(serial_terminal: SerialTerminal, imu_plotter, root: tk.Tk):
    """Handle application closing."""
    print("Exiting")
    serial_terminal.close()
    if imu_plotter is not None:
        imu_plotter.close()
    root.quit()
    root.destroy()


def main():
    """Main application entry point."""
    root = tk.Tk()
    root.title("Submarine Control Terminal")
    root.geometry("1000x720")
    
    # Configure root grid layout - only top row now (serial terminal)
    root.grid_rowconfigure(0, weight=1)      # Top: serial terminal (expandable)
    root.grid_columnconfigure(0, weight=1)   # Left (expandable)
    root.grid_columnconfigure(1, weight=0)   # Right (buttons)
    
    # Top frame for serial terminal spanning both columns
    serial_frame = tk.Frame(master=root)
    serial_frame.grid(row=0, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
    serial_frame.grid_rowconfigure(0, weight=1)
    serial_frame.grid_columnconfigure(0, weight=1)
    
    # Right frame for buttons
    buttons_container = tk.Frame(master=root)
    buttons_container.grid(row=0, column=1, sticky="n", padx=5, pady=5)
    
    # Create serial terminal
    serial_terminal = SerialTerminal(master=serial_frame)
    
    # Create buttons in the button frame
    buttons_frame = tk.Frame(master=buttons_container)
    buttons_frame.grid(row=0, column=0, sticky="n")
    
    # Add IMU Plotter toggle button
    imu_button = tk.Button(
        master=buttons_frame,
        text="IMU Plotter",
        command=lambda: toggle_imu_plotter(serial_terminal),
    )
    imu_button.config(width=20)
    imu_button.grid(row=0, column=0, padx=2, pady=2)
    
    # Add ESC control button
    esc_button = tk.Button(
        master=buttons_frame,
        text="ESCs Control",
        command=lambda: toggle_esc_control(serial_terminal),
    )
    esc_button.config(width=20)
    esc_button.grid(row=1, column=0, padx=2, pady=2)
    
    # Add light control button
    light_button = tk.Button(
        master=buttons_frame,
        text="Light Control",
        command=lambda: toggle_light_control(serial_terminal),
    )
    light_button.config(width=20)
    light_button.grid(row=2, column=0, padx=2, pady=2)
    
    # Add control pad button
    control_pad_button = tk.Button(
        master=buttons_frame,
        text="Control Pad",
        command=lambda: toggle_control_pad(serial_terminal),
    )
    control_pad_button.config(width=20)
    control_pad_button.grid(row=3, column=0, padx=2, pady=2)
    
    # Register callback to update control apps when connection state changes
    serial_terminal.register_connection_state_callback(update_control_apps_state)
    
    # Register close handler
    def on_root_closing():
        global imu_plotter_window, imu_plotter_app
        if imu_plotter_window is not None:
            imu_plotter_window.destroy()
            imu_plotter_app = None
            imu_plotter_window = None
        on_closing(serial_terminal, None, root)
    
    root.protocol("WM_DELETE_WINDOW", on_root_closing)
    
    # Start the main loop
    root.mainloop()


if __name__ == "__main__":
    main()
