import tkinter as tk
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg


def update_plot():
    if root.winfo_exists():
        # Generate 1000 random sample points
        x = np.random.rand(1000)
        y = np.random.rand(1000)

        # Clear the plot and plot new data
        ax.clear()
        ax.scatter(x, y)

        # Draw the updated plot
        canvas.draw()

        # Schedule the function to run again after 20 milliseconds
        global after_id
        after_id = root.after(20, update_plot)


def on_closing():
    if after_id is not None:
        root.after_cancel(after_id)
    root.quit()  # This will exit the main loop
    root.destroy()


# Create the main application window
root = tk.Tk()
root.title("Non-blocking Plot Example")

# Create a Matplotlib figure and axis
fig, ax = plt.subplots()
canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().pack(side=tk.TOP, fill=tk.BOTH, expand=1)

# Create a text field for user input
entry = tk.Entry(root, width=50)
entry.pack(pady=20)

# Start the plot update loop
after_id = root.after(20, update_plot)

# Handle the window close event
root.protocol("WM_DELETE_WINDOW", on_closing)

# Start the main event loop
root.mainloop()
