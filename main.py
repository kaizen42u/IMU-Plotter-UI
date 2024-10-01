import re
import sys
import threading
import tkinter as tk
from time import sleep
from tkinter import ttk
import csv
import os
from datetime import datetime
from typing import List, Optional

import matplotlib
import pandas as pd
import serial
import serial.tools.list_ports

from serialHandler import serialHandler
from ansiEncoding import ANSI

from tkAutocompleteCombobox import tkAutocompleteCombobox
from tkPlotGraph import tkPlotGraph
from tkTerminal import tkTerminal

matplotlib.use("Agg")


SAVEDATA_FOLDER_PATH = "./savedata"
TERMINAL_MAX_WIDTH = 180
GRAPH_MAX_SAMPLES = 120
GRAPH_ACCEL_Y_LIMIT = 4
GRAPH_GYRO_Y_LIMIT = 3000
SERIAL_IMU_DATA_REGEX = r"\[IMU\] \[\s*(\d+) ms\], Acc: \[\s*([-.\d]+),\s*([-.\d]+),\s*([-.\d]+)\] G, Gyro: \[\s*([-.\d]+),\s*([-.\d]+),\s*([-.\d]+)\] DPS"
THREAD_PLOTTER_DRAW_GRAPH_INTERVAL = 0.05
THREAD_DATA_VIEWER_UPDATE_INTERVAL = 0.10


# Return a list of gestures
def get_gestures() -> list[str]:
    if not os.path.exists(SAVEDATA_FOLDER_PATH) or not os.listdir(SAVEDATA_FOLDER_PATH):
        return ["idle"]
    else:
        return [
            name
            for name in os.listdir(SAVEDATA_FOLDER_PATH)
            if os.path.isdir(os.path.join(SAVEDATA_FOLDER_PATH, name))
        ]


class SerialPlotterApp:

    def __init__(self, root: tk.Misc) -> None:
        self.root: tk.Misc = root
        self.killed: bool = False
        self.show_imu_data: bool = True
        self.show_model_result: bool = True

        self.serial: serialHandler = serialHandler()

        self.setup_ui()

        # Get a list of all available serial ports
        #! TODO: update `ports` on device change
        ports = self.serial.get_ports()
        self.port_selection_combobox.set_completion_list(ports)
        self.serial_connect_toggle_button_update()

        self.serial.set_line_received_callback(self.serial_line_received)
        self.serial.set_log_callback(self.serial_log)
        self.serial.set_ports_changed_callback(self.serial_ports_changed)

        # Attach event handler on new gesture selected
        def gesture_selected_create_folder(event: tk.Event) -> None:
            # Create directory if it doesn't exist
            os.makedirs(
                f"{SAVEDATA_FOLDER_PATH}/{self.gesture_selected_combobox.get()}",
                exist_ok=True,
            )
            self.terminal_show_message(
                f"Gesture selected: {ANSI.bCyan}{self.gesture_selected_combobox.get()}{ANSI.default}"
            )

        self.gesture_selected_combobox.bind(
            "<<ComboboxSelected>>", gesture_selected_create_folder
        )

        # Create threads to draw figures and serial port reading
        self.draw_graphs_thread = threading.Thread(target=self.draw_graphs)
        self.draw_graphs_thread.start()

    def setup_ui(self) -> None:

        # Create a dropdown menu for available ports
        self.port_selection_combobox = tkAutocompleteCombobox(
            master=self.root, state="readonly"
        )
        self.port_selection_combobox.grid(row=0, column=0)

        # Create serial connect/disconnect button
        self.serial_connect_toggle_button = tk.Button(
            master=self.root, text="null", command=self.serial_connect_toggle
        )
        self.serial_connect_toggle_button.config(width=20)
        self.serial_connect_toggle_button.grid(row=0, column=1)

        # Create terminal auto scroll checkbox
        self.terminal_auto_scroll_var = tk.BooleanVar(master=self.root, value=True)
        self.terminal_auto_scroll_checkbox = tk.Checkbutton(
            master=self.root,
            text="Auto Scroll",
            variable=self.terminal_auto_scroll_var,
            command=lambda: self.terminal.set_autoscroll(
                self.terminal_auto_scroll_var.get()
            ),
        )
        self.terminal_auto_scroll_checkbox.config(width=20)
        self.terminal_auto_scroll_checkbox.grid(row=0, column=2)

        # Create the serial terminal
        self.terminal = tkTerminal(master=self.root, width=TERMINAL_MAX_WIDTH)
        self.terminal.grid(row=1, column=0, columnspan=3)

        # Create figure to draw accelerometer data
        self.accelerometer_figure = tkPlotGraph(
            master=self.root, title="Acceleration (G)", max_samples=GRAPH_MAX_SAMPLES
        )
        self.accelerometer_figure.grid(row=2, column=0)
        self.accelerometer_figure.set_ylim(
            low=-GRAPH_ACCEL_Y_LIMIT, high=GRAPH_ACCEL_Y_LIMIT
        )

        # Create figure to draw gyroscope data
        self.gyroscope_figure = tkPlotGraph(
            master=self.root,
            title="Angular Velocity (DPS)",
            max_samples=GRAPH_MAX_SAMPLES,
        )
        self.gyroscope_figure.grid(row=2, column=1)
        self.gyroscope_figure.set_ylim(low=-GRAPH_GYRO_Y_LIMIT, high=GRAPH_GYRO_Y_LIMIT)

        # Create a frame containing options
        self.options_frame = tk.Frame(master=self.root)
        self.options_frame.grid_rowconfigure(index=0, weight=1)
        self.options_frame.grid_columnconfigure(index=0, weight=1)
        self.options_frame.grid(row=2, column=2)

        # Create show/hide IMU data button
        self.imu_data_toggle_button = tk.Button(
            master=self.options_frame,
            text="Hide IMU data",
            command=self.imu_data_toggle,
        )
        self.imu_data_toggle_button.config(width=20)
        self.imu_data_toggle_button.grid(row=0, column=0)

        # Create show/hide model result button
        self.model_result_toggle_button = tk.Button(
            master=self.options_frame,
            text="Hide model result",
            command=self.model_result_toggle,
        )
        self.model_result_toggle_button.config(width=20)
        self.model_result_toggle_button.grid(row=1, column=0)

        # Create save to .csv button, this saves the graph data as csv
        # Save to: "{folder_path}/gesture1/[datetime].csv", ..., "{folder_path}/gesture1/[datetime].csv".
        # Format: Time, aX, aY, aZ, gX, gY, gZ
        self.gesture_save_button = tk.Button(
            master=self.options_frame, text="Save as .csv", command=self.save_csv
        )
        self.gesture_save_button.config(width=20)
        self.gesture_save_button.grid(row=2, column=0)

        # Create a label for the gesture selection
        self.gesture_selected_label = tk.Label(
            master=self.options_frame, text="Selected Gesture:"
        )
        self.gesture_selected_label.grid(row=3, column=0)

        # Create gesture selection box
        self.gesture_selected_combobox = tkAutocompleteCombobox(self.options_frame)
        self.gesture_selected_combobox.set_completion_list(get_gestures())
        self.gesture_selected_combobox.grid(row=4, column=0)

        # Configure the grid to expand
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_columnconfigure(2, weight=1)

    def close(self) -> None:
        # Flag the process as dead and close serial port
        self.killed = True
        self.serial.close()

        self.draw_graphs_thread.join(timeout=1)
        if self.draw_graphs_thread.is_alive():
            print("draw_graphs_thread did not exit in time")

        #! TODO: Fix draw_graphs_thread not exiting.
        print("[W] Close terminal to exit the program.")

    def serial_line_received(self, line: str) -> None:
        self.update_graphs(line)
        self.update_terminal(line)

    def serial_log(self, message: str) -> None:
        self.terminal_show_message(message)

    def serial_ports_changed(self, ports: List[str]) -> None:
        self.port_selection_combobox.set_completion_list(
            list(set(self.port_selection_combobox.get_completion_list() + ports))
        )
        self.serial_connect_toggle_button_update()
        self.terminal_show_message(f"Ports changed: {ports}")

    def serial_connect_toggle_button_update(self) -> None:
        display_text = "Disconnect" if self.serial.is_connected() else "Connect"
        self.serial_connect_toggle_button.configure(text=display_text)

    def serial_connect_toggle(self) -> None:
        # If already connected, disconnect
        if self.serial.is_connected():
            self.serial.disconnect()
            self.serial_connect_toggle_button_update()
            return

        # Otherwise, try to connect
        self.reset_graphs()
        try:
            self.serial.connect(self.port_selection_combobox.get())
            self.serial_connect_toggle_button_update()

        except serial.SerialException as e:
            self.terminal_show_message(
                f"Could not open port [{self.port_selection_combobox.get()}]: {e}"
            )

    def save_csv(self) -> None:
        # Create directory if it doesn't exist
        os.makedirs(
            f"{SAVEDATA_FOLDER_PATH}/{self.gesture_selected_combobox.get()}",
            exist_ok=True,
        )
        # Create a filename with the current datetime
        filename = f"{SAVEDATA_FOLDER_PATH}/{self.gesture_selected_combobox.get()}/{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        # Open the file for writing
        with open(filename, mode="w", newline="") as file:
            writer = csv.writer(file)
            # Write the header
            writer.writerow(["Time", "aX", "aY", "aZ", "gX", "gY", "gZ"])

            # Write the data
            total_samples: int = len(self.accelerometer_figure.timestamp)
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
        self.terminal_show_message(f"Data saved to {filename}, {total_samples} samples")

    def imu_data_toggle(self) -> None:
        self.show_imu_data = not self.show_imu_data
        display_text = "Hide IMU data" if self.show_imu_data else "Show IMU data"
        self.imu_data_toggle_button.configure(text=display_text)

    def model_result_toggle(self) -> None:
        self.show_model_result = not self.show_model_result
        display_text = (
            "Hide model result" if self.show_model_result else "Show model result"
        )
        self.model_result_toggle_button.configure(text=display_text)

    def update_terminal(self, reading: str) -> None:
        is_imu_data: bool = reading.startswith("[IMU]")
        if is_imu_data and not self.show_imu_data:
            return

        is_model_result: bool = reading.startswith("[Res]")
        if is_model_result and not self.show_model_result:
            return

        self.terminal.write(reading + "\n")

    def update_graphs(self, reading: str) -> None:
        match = re.search(
            SERIAL_IMU_DATA_REGEX,
            reading,
        )
        if match:
            time, acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z = match.groups()

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
        self.accelerometer_figure.clear()
        self.gyroscope_figure.clear()

    def draw_graphs(self) -> None:
        while not self.killed:
            sleep(THREAD_PLOTTER_DRAW_GRAPH_INTERVAL)

            # Update graph
            try:
                self.accelerometer_figure.draw()
                self.gyroscope_figure.draw()

            except RuntimeError:
                self.terminal_show_message(str(sys.exc_info()))
                pass

            except Exception as err:
                self.terminal_show_message(f"Graphing Exception: {err}")
        print("Graphing thread exited")

    def terminal_show_message(self, message: str) -> None:
        self.terminal.write(f"{ANSI.bBrightMagenta}{message}{ANSI.default} \n")
        print(message)


class GestureData:
    name_label: tk.Label
    counts_label: tk.Label
    selected_label: tk.Label
    selected_samples_label: tk.Label
    selected_combobox: tkAutocompleteCombobox
    accelerometer_figure: tkPlotGraph
    gyroscope_figure: tkPlotGraph
    selected_file: Optional[str] = None


class DataViewerApp:

    def __init__(self, root: tk.Misc) -> None:
        self.root: tk.Misc = root
        self.killed: bool = False
        self.gestures: dict[str, GestureData] = {}
        self.ROW_OFFSET: int = 4

        self.setup_ui()
        self.populate_tables()

        self.update_thread = threading.Thread(target=self.update)
        self.update_thread.start()

    def update(self) -> None:
        while not self.killed:
            sleep(THREAD_DATA_VIEWER_UPDATE_INTERVAL)
            self.update_contents()

            # If new gesture is added, re-populate tables
            if len(self.gestures) != len(get_gestures()):
                self.populate_tables()

    def update_contents(self) -> None:
        for gesture in self.gestures:
            # Try to load all files in ./{savedata}/{gesture}/[files]
            self.gestures[gesture].selected_combobox.set_completion_list(
                self.get_gesture_files(gesture)
            )
            self.update_content(gesture)

    def setup_ui(self) -> None:
        # Create a canvas and a scrollbar
        self.canvas = tk.Canvas(self.root)
        self.scrollbar = tk.Scrollbar(
            self.root, orient="vertical", command=self.canvas.yview
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # Create a frame inside the canvas
        self.frame = tk.Frame(self.canvas)
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
        # Cleanup whatever is left off
        for gesture in self.gestures:
            if self.gestures[gesture].accelerometer_figure:
                self.gestures[gesture].accelerometer_figure.close()
            if self.gestures[gesture].gyroscope_figure:
                self.gestures[gesture].gyroscope_figure.close()
        self.gestures.clear()

        # Make new
        gestures = get_gestures()
        for gesture in gestures:
            self.gestures[gesture] = GestureData()
            self.populate_table(gesture)

    def populate_table(self, gesture: str) -> None:
        index = list(self.gestures.keys()).index(gesture)
        print(f"{index = }, {gesture = }")

        # The name of the gesture, aka folder name
        self.gestures[gesture].name_label = tk.Label(self.frame, text=gesture)
        self.gestures[gesture].name_label.grid(
            row=index * self.ROW_OFFSET, column=0, sticky="nsew"
        )

        # The total number of samples files in the folder
        self.gestures[gesture].counts_label = tk.Label(self.frame)
        self.gestures[gesture].counts_label.grid(
            row=index * self.ROW_OFFSET, column=1, sticky="nsew"
        )

        # Label for the selection combo box
        self.gestures[gesture].selected_label = tk.Label(self.frame, text="Selected: ")
        self.gestures[gesture].selected_label.grid(
            row=index * self.ROW_OFFSET + 1, column=0, sticky="nsew"
        )

        # Combobox for selecting one of the sample file to view
        self.gestures[gesture].selected_combobox = tkAutocompleteCombobox(
            self.frame, state="readonly"
        )
        self.gestures[gesture].selected_combobox.grid(
            row=index * self.ROW_OFFSET + 1, column=1
        )

        # Create figure to draw gyroscope data
        self.gestures[gesture].accelerometer_figure = tkPlotGraph(
            master=self.frame, title="Acceleration (G)"
        )
        self.gestures[gesture].accelerometer_figure.grid(
            row=index * self.ROW_OFFSET, column=2, rowspan=self.ROW_OFFSET
        )
        self.gestures[gesture].accelerometer_figure.set_ylim(
            -GRAPH_ACCEL_Y_LIMIT, GRAPH_ACCEL_Y_LIMIT
        )

        # Create figure to draw gyroscope data
        self.gestures[gesture].gyroscope_figure = tkPlotGraph(
            master=self.frame, title="Angular Velocity (DPS)"
        )
        self.gestures[gesture].gyroscope_figure.grid(
            row=index * self.ROW_OFFSET, column=3, rowspan=self.ROW_OFFSET
        )
        self.gestures[gesture].gyroscope_figure.set_ylim(
            -GRAPH_GYRO_Y_LIMIT, GRAPH_GYRO_Y_LIMIT
        )

        # How many sample points are there for this data
        self.gestures[gesture].selected_samples_label = tk.Label(self.frame)
        self.gestures[gesture].selected_samples_label.grid(
            row=index * self.ROW_OFFSET + 2, column=1, sticky="nsew"
        )

        # Draw graphs with the default selected sample
        selected_gesture_sample = self.gestures[gesture].selected_combobox.get()
        self.load_graph_data(gesture, selected_gesture_sample)

    def update_content(self, gesture: str) -> None:
        # Count the number of samples in one gesture
        self.gestures[gesture].counts_label.configure(
            text=f"{len(self.gestures[gesture].selected_combobox.get_completion_list())} item"
        )

        # Get the selected file
        selected_gesture_sample = self.gestures[gesture].selected_combobox.get()

        # Skip of nothing is selected or the selection has not changed
        if (
            not selected_gesture_sample
            or self.gestures[gesture].selected_file == selected_gesture_sample
        ):
            return

        # Update selection and draw the updated sample data
        self.gestures[gesture].selected_file = selected_gesture_sample
        self.load_graph_data(gesture, selected_gesture_sample)

    def load_graph_data(self, gesture: str, file_name: str) -> None:
        # Skip if it is not a valid file
        if not file_name:
            return

        # load data to DataFrame
        df = pd.read_csv(f"{SAVEDATA_FOLDER_PATH}/{gesture}/{file_name}")

        # Clear figure for reuse
        self.gestures[gesture].accelerometer_figure.clear()
        self.gestures[gesture].gyroscope_figure.clear()

        # Load data to plot
        for _, row in df.iterrows():
            accelerometer_data = {
                "x-axis": float(row["aX"]),
                "y-axis": float(row["aY"]),
                "z-axis": float(row["aZ"]),
            }
            self.gestures[gesture].accelerometer_figure.append_dict(
                row["Time"], accelerometer_data
            )

            gyroscope_data = {
                "x-axis": float(row["gX"]),
                "y-axis": float(row["gY"]),
                "z-axis": float(row["gZ"]),
            }
            self.gestures[gesture].gyroscope_figure.append_dict(
                row["Time"], gyroscope_data
            )

        self.gestures[gesture].accelerometer_figure.draw()
        self.gestures[gesture].gyroscope_figure.draw()

        # Show the number of samples for this graph
        self.gestures[gesture].selected_samples_label.configure(
            text=f"{len(df)} samples"
        )

    # Returns a list of files names that is inside the [gesture] folder
    @staticmethod
    def get_gesture_files(gesture: str) -> list[str]:
        folder_path = f"{SAVEDATA_FOLDER_PATH}/{gesture}"
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

    serial_app = SerialPlotterApp(tab1)
    viewer_app = DataViewerApp(tab2)
    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()
