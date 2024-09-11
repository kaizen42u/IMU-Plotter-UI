import tkinter as tk
from tkinter import ttk


def update_progress():
    current_value = progress_var.get()
    next_value = (current_value + 1) % 101  # Increment and reset to 0 after 100
    progress_var.set(next_value)
    root.after(100, update_progress)  # Schedule the function to run again after 100ms


# Create the main application window
root = tk.Tk()
root.title("Non-blocking Progress Bar Example")

# Create a progress bar widget
progress_var = tk.IntVar()
progressbar = ttk.Progressbar(
    root, orient="horizontal", length=300, mode="determinate", variable=progress_var
)
progressbar.pack(pady=20)

# Create a text field for user input
entry = tk.Entry(root, width=50)
entry.pack(pady=20)

# Start the progress bar update loop
update_progress()

# Start the main event loop
root.mainloop()
