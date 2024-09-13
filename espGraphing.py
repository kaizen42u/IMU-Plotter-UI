import re
import sys
import threading
import tkinter as tk
from time import sleep
from tkinter import Misc, Text, ttk
import csv
import os
from datetime import datetime

import matplotlib
import serial
import serial.tools.list_ports

from ansiEncoding import ANSI

from tkPlotGraph import tkPlotGraph
from tkTerminal import tkTerminal

matplotlib.use("Agg")


class SerialApp:
    def __init__(self, root: Misc) -> None:
        self.root = root
        self.serial_port = None
        self.killed = False
        self.total_time = 0

        # Get a list of all available serial ports
        ports = self.get_ports()

        # Create a dropdown menu for available ports
        self.port_var = tk.StringVar()

        if ports:
            self.port_var.set(ports[0])  # Preselect the first available port
        self.port_dropdown = tk.OptionMenu(root, self.port_var, "", *ports)
        self.port_dropdown.config(width=20)
        self.port_dropdown.grid(row=0, column=0)

        # Create connect/disconnect button
        self.conn_button = tk.Button(root, text="Connect", command=self.connect_toggle)
        self.conn_button.config(width=20)
        self.conn_button.grid(row=0, column=1)

        # Create auto scroll checkbox
        self.auto_scroll = tk.BooleanVar(value=True)
        self.scroll_check = tk.Checkbutton(
            root,
            text="Auto Scroll",
            variable=self.auto_scroll,
            command=lambda: self.terminal.set_autoscroll(self.auto_scroll.get()),
        )
        self.scroll_check.config(width=20)
        self.scroll_check.grid(row=0, column=2)

        # Create the terminal
        self.terminal = tkTerminal(root, width=180)
        self.terminal.frame.grid(row=1, column=0, columnspan=3)

        # Create figures and a canvas to draw on
        self.accelerometer_figure = tkPlotGraph(root=root, title="Acceleration (G)")
        self.accelerometer_figure.grid(row=2, column=0)
        self.accelerometer_figure.set_ylim(-4, 4)

        self.gyroscope_figure = tkPlotGraph(root=root, title="Angular Velocity (DPS)")
        self.gyroscope_figure.grid(row=2, column=1)
        self.gyroscope_figure.set_ylim(-3000, 3000)

        # Create save to .csv button, this saves the graph data as csv
        # Save to: "savedata/gesture1/[datetime].csv", ..., "savedata/gesture1/[datetime].csv".
        # Format: Time, aX, aY, aZ, gX, gY, gZ
        self.save_button = tk.Button(root, text="Save as .csv", command=self.save_csv)
        self.save_button.config(width=20)
        self.save_button.grid(row=2, column=2)

        # Configure the grid to expand
        root.grid_rowconfigure(1, weight=1)
        root.grid_columnconfigure(0, weight=1)
        root.grid_columnconfigure(1, weight=1)
        root.grid_columnconfigure(2, weight=1)

        # Create threads to draw figures and serial port reading
        self.draw_graphs_thread = threading.Thread(target=self.draw_graphs)
        self.draw_graphs_thread.start()
        self.read_serial_thread = threading.Thread(target=self.read_from_port)
        self.read_serial_thread.start()

    def get_ports(self) -> list[str]:
        # Get a list of all available serial ports
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def close(self) -> None:
        # Flag the process as dead and close serial port
        self.killed = True
        self.disconnect_serial()

        # Attempt to join the draw_graphs_thread with a timeout
        self.draw_graphs_thread.join(timeout=1)
        if self.draw_graphs_thread.is_alive():
            print("draw_graphs_thread did not exit in time")

        # Attempt to join the read_serial_thread with a timeout
        self.read_serial_thread.join(timeout=1)
        if self.read_serial_thread.is_alive():
            print("read_serial_thread did not exit in time")

        #! TODO: Fix draw_graphs_thread not exiting.
        print("[W] Close terminal to exit the program.")

    def save_csv(self) -> None:
        # Create directory if it doesn't exist
        os.makedirs("savedata/gesture1", exist_ok=True)
        # Create a filename with the current datetime
        filename = f"savedata/gesture1/{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        # Open the file for writing
        with open(filename, mode="w", newline="") as file:
            writer = csv.writer(file)
            # Write the header
            writer.writerow(["Time", "aX", "aY", "aZ", "gX", "gY", "gZ"])

            # Write the data
            total_samples = len(self.accelerometer_figure.timestamp)
            for i in range(total_samples):
                writer.writerow(
                    [
                        self.accelerometer_figure.timestamp[i], # It is save to use timestamp from one graph only 
                        self.accelerometer_figure.data_series["x-axis"][i],
                        self.accelerometer_figure.data_series["y-axis"][i],
                        self.accelerometer_figure.data_series["z-axis"][i],
                        self.gyroscope_figure.data_series["x-axis"][i],
                        self.gyroscope_figure.data_series["y-axis"][i],
                        self.gyroscope_figure.data_series["z-axis"][i],
                    ]
                )
        self.show_message(f"Data saved to {filename}, {total_samples} samples")

    def connect_toggle(self) -> None:
        # If already connected, disconnect
        if self.serial_port and self.serial_port.is_open:
            self.disconnect_serial()
            return

        # Otherwise, try to connect
        self.reset_graphs()
        try:
            self.connect_serial()

        except serial.SerialException as e:
            self.show_message(f"Could not open port [{self.port_var.get()}]: {e}")

    def connect_serial(self):

        # Resets MCU
        self.serial_port = serial.Serial(self.port_var.get())
        self.serial_port.close()

        # Open port
        self.serial_port = serial.Serial(
            self.port_var.get(), baudrate=115200, timeout=1.0
        )
        self.conn_button.config(text="Disconnect")

        self.terminal.write(
            f"{ANSI.bBrightMagenta} Port [{self.port_var.get()}] Connected{ANSI.default}\n"
        )

    def disconnect_serial(self):
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            self.conn_button.config(text="Connect")
            self.terminal.write(
                f"{ANSI.bBrightMagenta} Port [{self.port_var.get()}] Disconnected{ANSI.default}\n"
            )

    def update_graphs(self, reading: str) -> None:
        match = re.search(
            r"\[IMU\] \[\s*(\d+) ms\], Acc: \[\s*([-.\d]+),\s*([-.\d]+),\s*([-.\d]+)\] G, Gyro: \[\s*([-.\d]+),\s*([-.\d]+),\s*([-.\d]+)\] DPS",
            reading,
        )
        if match:
            time, acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z = match.groups()
            self.total_time = self.total_time + int(time)

            accelerometer_data = {
                "x-axis": float(acc_x),
                "y-axis": float(acc_y),
                "z-axis": float(acc_z),
            }
            self.accelerometer_figure.append_dict(self.total_time, accelerometer_data)

            gyroscope_data = {
                "x-axis": float(gyro_x),
                "y-axis": float(gyro_y),
                "z-axis": float(gyro_z),
            }
            self.gyroscope_figure.append_dict(self.total_time, gyroscope_data)

    def reset_graphs(self) -> None:
        self.total_time = 0
        self.accelerometer_figure.clear()
        self.gyroscope_figure.clear()

    def draw_graphs(self) -> None:
        while not self.killed:
            sleep(0.05)

            # Update graph
            try:
                self.accelerometer_figure.draw()
                self.gyroscope_figure.draw()

            except RuntimeError:
                self.show_message(str(sys.exc_info()))
                pass

            except Exception as err:
                self.show_message(f"Graphing Exception: {err}")
        print("Graphing thread exited")

    def read_from_port(self) -> None:
        try:
            while not self.killed:
                sleep(0.05)

                # Reads serial port data by line
                while self.serial_port and self.serial_port.is_open:
                    try:
                        line = self.serial_port.readline()

                        # Check if line is not empty
                        if not line:
                            break

                        reading = line.decode("utf-8")
                        self.update_graphs(reading)
                        self.terminal.write(reading)

                    except serial.SerialException as serr:
                        self.disconnect_serial()
                        self.show_message(
                            f"Could not read port [{self.port_var.get()}]: {serr}"
                        )

                    except TypeError as terr:
                        self.show_message(
                            f"Bad serial data for port [{self.port_var.get()}]: {terr}"
                        )

                    except Exception as err:
                        self.show_message(f"Serial Exception: {err}")

            print("Serial Port thread exiting")
        except Exception as err:
            self.show_message(
                f"### Serial Port thread killed, trying to restart: {err} ###"
            )
            self.read_serial_thread = threading.Thread(target=self.read_from_port)
            self.read_serial_thread.start()

    def show_message(self, msg: str) -> None:
        self.terminal.write(f"{ANSI.bBrightMagenta}{msg}{ANSI.default}\n")
        print(msg)


def on_closing():
    print("Exiting")
    app.close()
    root.quit()  # This will exit the main loop
    root.destroy()


if __name__ == "__main__":

    root = tk.Tk()
    root.title("IMU Plotter")
    root.geometry("1280x720")

    tabControl = ttk.Notebook(root)
    tab1 = ttk.Frame(tabControl)
    tab2 = ttk.Frame(tabControl)

    tabControl.add(tab1, text="Main")
    tabControl.add(tab2, text="Data Viewer (dummy)")
    tabControl.pack(expand=1, fill="both")

    app = SerialApp(tab1)
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
