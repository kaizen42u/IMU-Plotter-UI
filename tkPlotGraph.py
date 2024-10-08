from tkinter import Misc

import matplotlib
import matplotlib.lines
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from collections import deque
import numpy as np

matplotlib.use("Agg")


class tkPlotGraph:
    def __init__(
        self,
        master: Misc,
        figsize: tuple[int, int] = (5, 4),
        dpi: int = 80,
        timespan: int | float | None = None,
        max_samples: int | None = None,
        title: str = "Graph",
        show_percentiles: bool = False,
    ) -> None:

        # Create a figure and a canvas to draw on
        self.figure = plt.figure(figsize=figsize, dpi=dpi)
        self.canvas = FigureCanvasTkAgg(self.figure, master=master)
        self.timespan = timespan
        self.max_samples = max_samples
        self.title = title

        # Graph data
        self.data_series: dict[str, deque[int | float]] = {}
        self.timestamp: deque[int | float] = deque()
        self.do_ylim: bool = False
        self.data_modified: bool = False

        # Configure Axes object
        self.ax = self.figure.add_subplot(111)
        self.ax.set_title(self.title)
        if self.do_ylim:
            self.ax.set_ylim(self.low_ylim, self.high_ylim)
        self.ax.grid()

        # Percentiles
        self.show_percentiles = show_percentiles
        self.high_percentile_line = self.ax.axhline(color="#D3D3D3", linestyle="--")
        self.median_line = self.ax.axhline(color="#D3D3D3", linestyle="--")
        self.low_percentile_line = self.ax.axhline(color="#D3D3D3", linestyle="--")

        # Initialize line objects
        self.lines = {}

    # Partial function of tk.grid()
    def grid(self, row: int = 0, column: int = 0, **kwargs) -> None:
        self.canvas.get_tk_widget().grid(row=row, column=column, **kwargs)

    def close(self):
        plt.close(fig=self.figure)

    # Clears graph data
    def clear(self) -> None:
        self.data_series.clear()
        self.data_modified = True
        self.timestamp.clear()
        self.lines.clear()
        self.ax.clear()  # Clear the axes
        self.ax.set_title(self.title)  # Reset the title
        self.high_percentile_line = self.ax.axhline(color="gray", linestyle="--")
        self.median_line = self.ax.axhline(color="gray", linestyle="--")
        self.low_percentile_line = self.ax.axhline(color="gray", linestyle="--")
        self.ax.grid()  # Reset the grid

    # Appends timestamp and data to the list, also clears old data
    def append_dict(
        self, timestamp: int | float, data_dict: dict[str, int | float]
    ) -> None:
        self.timestamp.append(timestamp)
        for label, data in data_dict.items():
            if label not in self.data_series:
                self.data_series[label] = deque()
                (self.lines[label],) = self.ax.plot([], [], label=label)
            self.data_series[label].append(data)

        self.remove_old_data(timestamp)
        self.limit_sample_size()
        self.data_modified = True

    # Appends timestamp and a list of data to the list, also clears old data
    def append_list(self, timestamp: int | float, data_list: list[int | float]) -> None:
        self.timestamp.append(timestamp)
        for i, data in enumerate(data_list):
            label = f"Series {i+1}"
            if label not in self.data_series:
                self.data_series[label] = deque()
                (self.lines[label],) = self.ax.plot([], [], label=label)
            self.data_series[label].append(data)

        self.remove_old_data(timestamp)
        self.limit_sample_size()
        self.data_modified = True

    # Appends timestamp and a single data point to the list, also clears old data
    def append_single(self, timestamp: int | float, data: int | float) -> None:
        self.timestamp.append(timestamp)
        label = "Series 1"
        if label not in self.data_series:
            self.data_series[label] = deque()
            (self.lines[label],) = self.ax.plot([], [], label=label)
        self.data_series[label].append(data)

        self.remove_old_data(timestamp)
        self.limit_sample_size()
        self.data_modified = True

    # Remove data older than x milliseconds
    def remove_old_data(self, timestamp: int | float) -> None:
        if self.timespan is None:
            return

        while self.timestamp and self.timestamp[0] < timestamp - self.timespan:
            self.timestamp.popleft()
            for series in self.data_series.values():
                series.popleft()

    # Limit the number of samples in the plot
    def limit_sample_size(self) -> None:
        if self.max_samples is None:
            return

        while len(self.timestamp) > self.max_samples:
            self.timestamp.popleft()
            for series in self.data_series.values():
                series.popleft()

    # Set graph y-axis limit, default is automatic
    def set_ylim(self, low: int | float, high: int | float):
        self.do_ylim = True
        self.low_ylim = low
        self.high_ylim = high

    def calculate_percentiles(self):
        all_values = []

        for series in self.data_series.values():
            all_values.extend(series)

        if all_values:
            self.high_percentile = np.percentile(all_values, 75)
            self.median = np.percentile(all_values, 50)
            self.low_percentile = np.percentile(all_values, 25)
        else:
            self.high_percentile = 0
            self.median = 0
            self.low_percentile = 0

    # Draw graph on canvas
    def draw(self) -> None:
        if not self.data_modified:
            return

        # Draw percentile lines
        self.calculate_percentiles()
        if self.show_percentiles:
            self.high_percentile_line.set_ydata(np.array([self.high_percentile]))
            self.median_line.set_ydata(np.array([self.median]))
            self.low_percentile_line.set_ydata(np.array([self.low_percentile]))
            self.high_percentile_line.set_visible(True)
            self.median_line.set_visible(True)
            self.low_percentile_line.set_visible(True)
        else:
            self.high_percentile_line.set_visible(False)
            self.median_line.set_visible(False)
            self.low_percentile_line.set_visible(False)

        # Draw data
        for label, series in self.data_series.items():
            self.lines[label].set_data(self.timestamp, series)

        # Rescale the x-axis to fit the new data
        if len(self.timestamp) >= 2:
            self.ax.set_xlim(self.timestamp[0], self.timestamp[-1])

        # Rescale the y-axis to fit the new data
        if self.do_ylim:
            self.ax.set_ylim(self.low_ylim, self.high_ylim)
        else:
            self.ax.relim()
            self.ax.autoscale_view(scalex=False)

        if self.data_series:
            self.ax.legend()
        self.canvas.draw()


def main():
    from tkinter import Tk
    import random
    import time

    root = Tk()

    figure1 = tkPlotGraph(master=root, timespan=3000, title="Test Append Dict")
    figure1.grid(row=0, column=0)
    figure1.set_ylim(-4, 4)

    figure2 = tkPlotGraph(master=root, timespan=3000, title="Test Append List")
    figure2.grid(row=0, column=1)
    figure2.set_ylim(-4, 4)

    figure3 = tkPlotGraph(master=root, timespan=3000, title="Test Append Single")
    figure3.grid(row=0, column=2)
    figure3.set_ylim(-4, 4)

    start_time = time.time()

    def update_figure_data():
        update_figure1_data()
        update_figure2_data()
        update_figure3_data()
        draw_figures()
        root.after(100, update_figure_data)

    def draw_figures():
        figure1.draw()
        figure2.draw()
        figure3.draw()

    def update_figure1_data():
        current_time = time.time()  # Current time in milliseconds
        time_since_start_ms = (current_time - start_time) * 1000
        data = {
            "Series 1": random.uniform(-3, 3),
            "Series 2": random.uniform(-3, 3),
            "Series 3": random.uniform(-3, 3),
        }
        figure1.append_dict(time_since_start_ms, data)

    def update_figure2_data():
        current_time = time.time()  # Current time in milliseconds
        time_since_start_ms = (current_time - start_time) * 1000
        data = [
            random.uniform(-3, 3),
            random.uniform(-3, 3),
            random.uniform(-3, 3),
        ]
        figure2.append_list(time_since_start_ms, data)

    def update_figure3_data():
        current_time = time.time()  # Current time in milliseconds
        time_since_start_ms = (current_time - start_time) * 1000
        data = random.uniform(-3, 3)
        figure3.append_single(time_since_start_ms, data)

    update_figure_data()
    draw_figures()
    root.mainloop()


# Example usage
if __name__ == "__main__":
    main()
