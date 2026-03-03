"""Main entry point for IMU Plotter UI application."""

import tkinter as tk
from typing import Optional

from apps.serialTerminal import SerialTerminal
from apps.imuPlotter import IMUPlotter
from apps.mpu6050Plotter import MPU6050Plotter
from apps.escControlApp import ESCControlApp
from apps.lightControlApp import LightControlApp
from apps.controlPadApp import ControlPadApp
from apps.vc288App import VC288App
from apps.leakageApp import LeakageApp


# Global references for control apps
esc_control_app: Optional[ESCControlApp] = None
light_control_app: Optional[LightControlApp] = None
control_pad_app: Optional[ControlPadApp] = None
vc288_app: Optional[VC288App] = None
leakage_app: Optional[LeakageApp] = None
imu_plotter_window: Optional[tk.Toplevel] = None
imu_plotter_app: Optional[IMUPlotter] = None
mpu6050_plotter_window: Optional[tk.Toplevel] = None
mpu6050_plotter_app: Optional[MPU6050Plotter] = None


def toggle_window(
    app_key: str,
    create_func,
    post_create_func=None,
    post_toggle_func=None,
):
    """Generic window toggle function to reduce duplication.
    
    Args:
        app_key: Key to access app in globals()
        create_func: Function to create the app
        post_create_func: Optional function to call after app creation
        post_toggle_func: Optional function to call when toggling existing app
    """
    app_ref = globals()
    app = app_ref.get(app_key)
    
    if app is None or not app.window.winfo_exists():
        app = create_func()
        app_ref[app_key] = app
        
        # Generic close handler
        def on_window_close():
            if app_ref.get(app_key) is not None:
                app_ref[app_key].window.withdraw()
        
        app.window.protocol("WM_DELETE_WINDOW", on_window_close)
        
        if post_create_func:
            post_create_func(app)
    else:
        if post_toggle_func:
            post_toggle_func(app)
        
        # Toggle visibility
        if app.window.winfo_viewable():
            app.window.withdraw()
        else:
            app.window.deiconify()
            app.window.lift()


def toggle_esc_control(serial_terminal: SerialTerminal):
    """Toggle ESC control window visibility."""
    global esc_control_app, control_pad_app

    def create_esc():
        return ESCControlApp(parent=serial_terminal.master, serial_terminal=serial_terminal)

    def post_create(app):
        if control_pad_app is not None:
            control_pad_app.set_esc_control_app(app)

    def post_toggle(app):
        if control_pad_app is not None:
            control_pad_app.set_esc_control_app(app)

    toggle_window("esc_control_app", create_esc, post_create, post_toggle)


def toggle_light_control(serial_terminal: SerialTerminal):
    """Toggle light control window visibility."""
    global light_control_app, control_pad_app

    def create_light():
        return LightControlApp(parent=serial_terminal.master, serial_terminal=serial_terminal)

    def post_create(app):
        if control_pad_app is not None:
            control_pad_app.set_light_control_app(app)

    def post_toggle(app):
        if control_pad_app is not None:
            control_pad_app.set_light_control_app(app)

    toggle_window("light_control_app", create_light, post_create, post_toggle)


def toggle_control_pad(serial_terminal: SerialTerminal):
    """Toggle control pad window visibility."""
    global control_pad_app

    def create_pad():
        return ControlPadApp(
            parent=serial_terminal.master,
            serial_terminal=serial_terminal,
            light_control_app=light_control_app,
            esc_control_app=esc_control_app,
        )

    def post_toggle(app):
        app.set_light_control_app(light_control_app)
        app.set_esc_control_app(esc_control_app)

    toggle_window("control_pad_app", create_pad, None, post_toggle)


def toggle_imu_plotter(serial_terminal: SerialTerminal):
    """Toggle IMU plotter window visibility."""
    global imu_plotter_window, imu_plotter_app

    def create_imu():
        global imu_plotter_window, imu_plotter_app
        imu_plotter_window = tk.Toplevel()
        imu_plotter_window.title("IMU Plotter")

        imu_frame = tk.Frame(master=imu_plotter_window)
        imu_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        imu_plotter_app = IMUPlotter(master=imu_frame, serial_terminal=serial_terminal)

        # Auto-size window to fit content
        imu_plotter_window.update_idletasks()
        width = imu_frame.winfo_reqwidth() + 10
        height = imu_frame.winfo_reqheight() + 10
        imu_plotter_window.geometry(f"{width}x{height}")
        
        # Create a wrapper object with .window attribute for compatibility with toggle_window
        class IMUPlotterWrapper:
            def __init__(self, window):
                self.window = window
            
            def destroy(self):
                """Destroy the window."""
                self.window.destroy()
        
        return IMUPlotterWrapper(imu_plotter_window)

    toggle_window("imu_plotter_window", create_imu)


def toggle_mpu6050_plotter(serial_terminal: SerialTerminal):
    """Toggle MPU6050 plotter window visibility."""
    global mpu6050_plotter_window, mpu6050_plotter_app

    def create_mpu6050():
        global mpu6050_plotter_window, mpu6050_plotter_app
        mpu6050_plotter_window = tk.Toplevel()
        mpu6050_plotter_window.title("MPU6050 Plotter")

        mpu6050_frame = tk.Frame(master=mpu6050_plotter_window)
        mpu6050_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        mpu6050_plotter_app = MPU6050Plotter(master=mpu6050_frame, serial_terminal=serial_terminal)

        # Auto-size window to fit content
        mpu6050_plotter_window.update_idletasks()
        width = mpu6050_frame.winfo_reqwidth() + 10
        height = mpu6050_frame.winfo_reqheight() + 10
        mpu6050_plotter_window.geometry(f"{width}x{height}")
        
        # Create a wrapper object with .window attribute for compatibility with toggle_window
        class MPU6050PlotterWrapper:
            def __init__(self, window):
                self.window = window
            
            def destroy(self):
                """Destroy the window."""
                self.window.destroy()
        
        return MPU6050PlotterWrapper(mpu6050_plotter_window)

    toggle_window("mpu6050_plotter_window", create_mpu6050)


def toggle_vc288(serial_terminal: SerialTerminal):
    """Toggle VC288 sensor window visibility."""
    global vc288_app

    def create_vc288():
        return VC288App(parent=serial_terminal)

    toggle_window("vc288_app", create_vc288)


def toggle_leakage(serial_terminal: SerialTerminal):
    """Toggle Leakage sensor window visibility."""
    global leakage_app

    def create_leakage():
        return LeakageApp(parent=serial_terminal)

    toggle_window("leakage_app", create_leakage)


def update_control_apps_state():
    """Update control apps when connection state changes."""
    if esc_control_app and esc_control_app.window.winfo_exists():
        esc_control_app.update_connection_state()
    if light_control_app and light_control_app.window.winfo_exists():
        light_control_app.update_connection_state()
    if vc288_app and vc288_app.window.winfo_exists():
        vc288_app.update_connection_state()
    if leakage_app and leakage_app.window.winfo_exists():
        leakage_app.update_connection_state()


def on_closing(serial_terminal: SerialTerminal, imu_plotter, root: tk.Tk):
    """Handle application closing."""
    print("Exiting")

    # Save and close ESC control app if exists
    if esc_control_app and esc_control_app.window.winfo_exists():
        esc_control_app.on_window_close()

    # Save and close light control app if exists
    if light_control_app and light_control_app.window.winfo_exists():
        light_control_app.on_window_close()

    # Close other apps
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
    root.grid_rowconfigure(0, weight=1)  # Top: serial terminal (expandable)
    root.grid_columnconfigure(0, weight=1)  # Left (expandable)
    root.grid_columnconfigure(1, weight=0)  # Right (buttons)

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
        text="IMU Plotter (BNO085)",
        command=lambda: toggle_imu_plotter(serial_terminal),
    )
    imu_button.config(width=20)
    imu_button.grid(row=0, column=0, padx=2, pady=2)

    # Add MPU6050 Plotter toggle button
    mpu6050_button = tk.Button(
        master=buttons_frame,
        text="MPU6050 Plotter",
        command=lambda: toggle_mpu6050_plotter(serial_terminal),
    )
    mpu6050_button.config(width=20)
    mpu6050_button.grid(row=1, column=0, padx=2, pady=2)

    # Add ESC control button
    esc_button = tk.Button(
        master=buttons_frame,
        text="ESCs Control",
        command=lambda: toggle_esc_control(serial_terminal),
    )
    esc_button.config(width=20)
    esc_button.grid(row=2, column=0, padx=2, pady=2)

    # Add light control button
    light_button = tk.Button(
        master=buttons_frame,
        text="Light Control",
        command=lambda: toggle_light_control(serial_terminal),
    )
    light_button.config(width=20)
    light_button.grid(row=3, column=0, padx=2, pady=2)

    # Add control pad button
    control_pad_button = tk.Button(
        master=buttons_frame,
        text="Control Pad",
        command=lambda: toggle_control_pad(serial_terminal),
    )
    control_pad_button.config(width=20)
    control_pad_button.grid(row=4, column=0, padx=2, pady=2)

    # Add VC288 sensor button
    vc288_button = tk.Button(
        master=buttons_frame,
        text="VC288 Sensor",
        command=lambda: toggle_vc288(serial_terminal),
    )
    vc288_button.config(width=20)
    vc288_button.grid(row=5, column=0, padx=2, pady=2)

    # Add Leakage sensor button
    leakage_button = tk.Button(
        master=buttons_frame,
        text="Leakage Sensor",
        command=lambda: toggle_leakage(serial_terminal),
    )
    leakage_button.config(width=20)
    leakage_button.grid(row=6, column=0, padx=2, pady=2)

    # Register callback to update control apps when connection state changes
    serial_terminal.register_connection_state_callback(update_control_apps_state)

    # Register close handler
    def on_root_closing():
        global imu_plotter_window, imu_plotter_app, mpu6050_plotter_window, mpu6050_plotter_app
        if imu_plotter_window is not None:
            imu_plotter_window.destroy()
            imu_plotter_app = None
            imu_plotter_window = None
        if mpu6050_plotter_window is not None:
            mpu6050_plotter_window.destroy()
            mpu6050_plotter_app = None
            mpu6050_plotter_window = None
        on_closing(serial_terminal, None, root)

    root.protocol("WM_DELETE_WINDOW", on_root_closing)

    # Start the main loop
    root.mainloop()


if __name__ == "__main__":
    main()
