import re
import sys
import threading
import tkinter as tk
from time import sleep
from tkinter import Button, Canvas, Event, Frame, Label, Misc, Scrollbar, Text, ttk
import csv
import os
from datetime import datetime

import matplotlib
import pandas as pd
import serial
import serial.tools.list_ports

from ansiEncoding import ANSI

from tkAutocompleteCombobox import tkAutocompleteCombobox
from tkPlotGraph import tkPlotGraph
from tkTerminal import tkTerminal

matplotlib.use("Agg")


def get_gesture_list() -> list[str]:
    folder_path = "./savedata"
    if not os.path.exists(folder_path) or not os.listdir(folder_path):
        return ["idle"]
    else:
        return [
            name
            for name in os.listdir(folder_path)
            if os.path.isdir(os.path.join(folder_path, name))
        ]


class SerialApp:

    def __init__(self, root: Misc) -> None:
        self.root = root
        self.serial_port = None
        self.killed = False
        self.show_imu_data = True
        self.show_model_result = True
        # self.total_time = 0

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
        self.accelerometer_figure = tkPlotGraph(
            root=root, title="Acceleration (G)", max_samples=120
        )
        self.accelerometer_figure.grid(row=2, column=0)
        self.accelerometer_figure.set_ylim(-4, 4)

        self.gyroscope_figure = tkPlotGraph(
            root=root, title="Angular Velocity (DPS)", max_samples=120
        )
        self.gyroscope_figure.grid(row=2, column=1)
        self.gyroscope_figure.set_ylim(-3000, 3000)

        self.save_option_frame = Frame(root)
        self.save_option_frame.grid_rowconfigure(0, weight=1)
        self.save_option_frame.grid_columnconfigure(0, weight=1)
        self.save_option_frame.grid(row=2, column=2)

        # Create show/hide IMU data button
        self.imu_data_toggle_button = tk.Button(
            self.save_option_frame, text="Hide IMU data", command=self.imu_data_toggle
        )
        self.imu_data_toggle_button.config(width=20)
        self.imu_data_toggle_button.grid(row=0, column=0)

        # Create show/hide model result button
        self.model_result_toggle_button = tk.Button(
            self.save_option_frame,
            text="Hide model result",
            command=self.model_result_toggle,
        )
        self.model_result_toggle_button.config(width=20)
        self.model_result_toggle_button.grid(row=1, column=0)

        # Create save to .csv button, this saves the graph data as csv
        # Save to: "savedata/gesture1/[datetime].csv", ..., "savedata/gesture1/[datetime].csv".
        # Format: Time, aX, aY, aZ, gX, gY, gZ
        self.gesture_save_button = tk.Button(
            self.save_option_frame, text="Save as .csv", command=self.save_csv
        )
        self.gesture_save_button.config(width=20)
        self.gesture_save_button.grid(row=2, column=0)

        self.gesture_selected_label = tk.Label(
            self.save_option_frame, text="Selected Gesture:"
        )
        self.gesture_selected_label.grid(row=3, column=0)

        def gesture_select(event: Event) -> None:
            # Create directory if it doesn't exist
            os.makedirs(
                f"savedata/{self.gesture_selected_combobox.get()}", exist_ok=True
            )
            self.show_message(
                f"Gesture selected: {ANSI.bCyan}{self.gesture_selected_combobox.get()}{ANSI.default}"
            )

        self.gesture_selected_combobox = tkAutocompleteCombobox(self.save_option_frame)
        self.gesture_selected_combobox.set_completion_list(get_gesture_list())
        self.gesture_selected_combobox.grid(row=4, column=0)
        self.gesture_selected_combobox.bind("<<ComboboxSelected>>", gesture_select)

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
        os.makedirs(f"savedata/{self.gesture_selected_combobox.get()}", exist_ok=True)
        # Create a filename with the current datetime
        filename = f"savedata/{self.gesture_selected_combobox.get()}/{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

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
                        self.accelerometer_figure.timestamp[
                            i
                        ],  # It is save to use timestamp from one graph only
                        self.accelerometer_figure.data_series["x-axis"][i],
                        self.accelerometer_figure.data_series["y-axis"][i],
                        self.accelerometer_figure.data_series["z-axis"][i],
                        self.gyroscope_figure.data_series["x-axis"][i],
                        self.gyroscope_figure.data_series["y-axis"][i],
                        self.gyroscope_figure.data_series["z-axis"][i],
                    ]
                )
        self.show_message(f"Data saved to {filename}, {total_samples} samples")

    def imu_data_toggle(self) -> None:
        if self.show_imu_data:
            self.show_imu_data = False
            self.imu_data_toggle_button.configure(text="Show IMU data")
        else:
            self.show_imu_data = True
            self.imu_data_toggle_button.configure(text="Hide IMU data")

    def model_result_toggle(self) -> None:
        if self.show_model_result:
            self.show_model_result = False
            self.model_result_toggle_button.configure(text="Show model result")
        else:
            self.show_model_result = True
            self.model_result_toggle_button.configure(text="Hide model result")

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

    def update_terminal(self, reading: str) -> None:
        is_imu = reading.startswith("[IMU]")
        if is_imu and not self.show_imu_data:
            return

        is_model_result = reading.startswith("[Result]")
        if is_model_result and not self.show_model_result:
            return

        self.terminal.write(reading)

    def update_graphs(self, reading: str) -> None:
        match = re.search(
            r"\[IMU\] \[\s*(\d+) ms\], Acc: \[\s*([-.\d]+),\s*([-.\d]+),\s*([-.\d]+)\] G, Gyro: \[\s*([-.\d]+),\s*([-.\d]+),\s*([-.\d]+)\] DPS",
            reading,
        )
        if match:
            time, acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z = match.groups()
            # self.total_time = self.total_time + int(time)

            accelerometer_data = {
                "x-axis": float(acc_x),
                "y-axis": float(acc_y),
                "z-axis": float(acc_z),
            }
            self.accelerometer_figure.append_dict(int(time), accelerometer_data)

            gyroscope_data = {
                "x-axis": float(gyro_x),
                "y-axis": float(gyro_y),
                "z-axis": float(gyro_z),
            }
            self.gyroscope_figure.append_dict(int(time), gyroscope_data)

    def reset_graphs(self) -> None:
        # self.total_time = 0
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
                        self.update_terminal(reading)

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
        self.terminal.write(f"{ANSI.bBrightMagenta}{msg}{ANSI.default} \n")
        print(msg)


class DataViewerApp:
    def __init__(self, root: tk.Misc) -> None:
        self.root = root
        self.killed = False
        self.gestures = get_gesture_list()
        self.gesture_name_label: dict[str, Label] = {}
        self.gesture_counts_label: dict[str, Label] = {}
        self.gesture_selected_label: dict[str, Label] = {}
        self.gesture_files: dict[str, list[str]] = {}
        self.gesture_selected_samples_label: dict[str, Label] = {}
        self.gesture_selected_combobox: dict[str, tkAutocompleteCombobox] = {}
        self.accelerometer_figures: dict[str, tkPlotGraph] = {}
        self.gyroscope_figures: dict[str, tkPlotGraph] = {}
        self.old_selected_gestures: dict[str, str] = {}
        self.row_offset = 4

        self.setup_ui()
        self.populate_tables()

        self.update_thread = threading.Thread(target=self.update)
        self.update_thread.start()

    def update(self) -> None:
        while not self.killed:
            sleep(0.1)
            self.update_contents()

            if len(self.gestures) != len(get_gesture_list()):
                self = DataViewerApp(self.root)

    def update_contents(self) -> None:
        for gesture in self.gestures:
            self.gesture_files[gesture] = self.get_gesture_files(gesture)
            # print(f"{self.gesture_files[gesture] = }")
            self.update_content(gesture)

    def setup_ui(self) -> None:
        # Create a canvas and a scrollbar
        self.canvas = Canvas(self.root)
        self.scrollbar = Scrollbar(
            self.root, orient="vertical", command=self.canvas.yview
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # Create a frame inside the canvas
        self.frame = Frame(self.canvas)
        self.canvas.create_window((0, 0), window=self.frame, anchor="nw")

        # Configure the grid to expand
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Update the scroll region
        self.frame.bind("<Configure>", self.on_frame_configure)

    def close(self):
        self.killed = True

        self.update_thread.join(timeout=1)
        if self.update_thread.is_alive():
            print("update_thread did not exit in time")

    def populate_tables(self) -> None:
        for gesture in self.gestures:
            self.gesture_files[gesture] = self.get_gesture_files(gesture)
            self.populate_table(gesture)

    def populate_table(self, gesture: str) -> None:
        index = self.gestures.index(gesture)
        print(f"{index = }, {gesture = }, {len(self.gesture_files[gesture]) = }")

        self.gesture_name_label[gesture] = Label(self.frame, text=gesture)
        self.gesture_name_label[gesture].grid(
            row=index * self.row_offset, column=0, sticky="nsew"
        )

        self.gesture_counts_label[gesture] = Label(self.frame)
        self.gesture_counts_label[gesture].grid(
            row=index * self.row_offset, column=1, sticky="nsew"
        )

        self.gesture_selected_label[gesture] = Label(self.frame, text="Selected: ")
        self.gesture_selected_label[gesture].grid(
            row=index * self.row_offset + 1, column=0, sticky="nsew"
        )

        self.gesture_selected_combobox[gesture] = tkAutocompleteCombobox(
            self.frame, state="readonly"
        )
        self.gesture_selected_combobox[gesture].set_completion_list(
            self.gesture_files[gesture]
        )
        self.gesture_selected_combobox[gesture].grid(
            row=index * self.row_offset + 1, column=1
        )

        # Create figures and a canvas to draw on
        self.accelerometer_figures[gesture] = tkPlotGraph(
            root=self.frame, title="Acceleration (G)"
        )
        self.accelerometer_figures[gesture].grid(
            row=index * self.row_offset, column=2, rowspan=self.row_offset
        )
        self.accelerometer_figures[gesture].set_ylim(-4, 4)

        self.gyroscope_figures[gesture] = tkPlotGraph(
            root=self.frame, title="Angular Velocity (DPS)"
        )
        self.gyroscope_figures[gesture].grid(
            row=index * self.row_offset, column=3, rowspan=self.row_offset
        )
        self.gyroscope_figures[gesture].set_ylim(-3000, 3000)

        self.gesture_selected_samples_label[gesture] = Label(self.frame)
        self.gesture_selected_samples_label[gesture].grid(
            row=index * self.row_offset + 2, column=1, sticky="nsew"
        )

        selected_gesture = self.gesture_selected_combobox[gesture].get()
        if selected_gesture:
            # load data to DataFrame
            df = pd.read_csv(f"./savedata/{gesture}/{selected_gesture}")

            self.accelerometer_figures[gesture].clear()
            self.gyroscope_figures[gesture].clear()

            # Load data to plot
            for _, row in df.iterrows():
                accelerometer_data = {
                    "x-axis": float(row["aX"]),
                    "y-axis": float(row["aY"]),
                    "z-axis": float(row["aZ"]),
                }
                self.accelerometer_figures[gesture].append_dict(
                    row["Time"], accelerometer_data
                )

                gyroscope_data = {
                    "x-axis": float(row["gX"]),
                    "y-axis": float(row["gY"]),
                    "z-axis": float(row["gZ"]),
                }
                self.gyroscope_figures[gesture].append_dict(row["Time"], gyroscope_data)

            self.accelerometer_figures[gesture].draw()
            self.gyroscope_figures[gesture].draw()

    def update_content(self, gesture: str) -> None:
        self.gesture_counts_label[gesture].configure(
            text=f"{len(self.gesture_files[gesture])} item"
        )
        self.gesture_selected_combobox[gesture].set_completion_list(
            self.gesture_files[gesture]
        )
        selected_gesture = self.gesture_selected_combobox[gesture].get()

        if (
            not selected_gesture
            or self.old_selected_gestures.get(gesture) == selected_gesture
        ):
            return
        self.old_selected_gestures[gesture] = self.gesture_selected_combobox[
            gesture
        ].get()

        # load data to DataFrame
        df = pd.read_csv(f"./savedata/{gesture}/{selected_gesture}")

        self.accelerometer_figures[gesture].clear()
        self.gyroscope_figures[gesture].clear()

        # Load data to plot
        for _, row in df.iterrows():
            accelerometer_data = {
                "x-axis": float(row["aX"]),
                "y-axis": float(row["aY"]),
                "z-axis": float(row["aZ"]),
            }
            self.accelerometer_figures[gesture].append_dict(
                row["Time"], accelerometer_data
            )

            gyroscope_data = {
                "x-axis": float(row["gX"]),
                "y-axis": float(row["gY"]),
                "z-axis": float(row["gZ"]),
            }
            self.gyroscope_figures[gesture].append_dict(row["Time"], gyroscope_data)

        self.accelerometer_figures[gesture].draw()
        self.gyroscope_figures[gesture].draw()
        self.gesture_selected_samples_label[gesture].configure(
            text=f"{len(df)} samples"
        )

    def get_gesture_files(self, gesture: str) -> list[str]:
        folder_path = f"./savedata/{gesture}"
        if not os.path.exists(folder_path) or not os.listdir(folder_path):
            return []
        else:
            return [
                name
                for name in os.listdir(folder_path)
                if os.path.isfile(os.path.join(folder_path, name))
            ]

    def on_frame_configure(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))


def on_closing():
    print("Exiting")
    serial_app.close()
    viewer_app.close()
    root.quit()  # This will exit the main loop
    root.destroy()


if __name__ == "__main__":

    root = tk.Tk()
    root.title("IMU Plotter")
    root.geometry("1280x720")

    tabControl = ttk.Notebook(root)
    tab1 = ttk.Frame(tabControl)
    tab2 = ttk.Frame(tabControl)

    tabControl.add(tab1, text="Serial Reader")
    tabControl.add(tab2, text="Data Viewer")
    tabControl.pack(expand=1, fill="both")

    serial_app = SerialApp(tab1)
    viewer_app = DataViewerApp(tab2)
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
