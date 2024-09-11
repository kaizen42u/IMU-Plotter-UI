from time import sleep
from tkinter import ttk
import tkinter as tk


def start():
    button.configure(text="Stop", command=stop)
    label.configure(text="Working...")
    global interrupt
    interrupt = False
    root.after(1, step)


def stop():
    global interrupt
    interrupt = True


def step(count=0):
    progress_bar.configure(value=count)
    if interrupt:
        result(None)
        return
    sleep(0.05)  # next step in our operation; don't take too long!
    if count == 20:  # done!
        result(42)
        return
    root.after(1, lambda: step(count + 1))


def result(answer):
    progress_bar.configure(value=0)
    button.configure(text="Start!", command=start)
    label.configure(text="Answer: " + str(answer) if answer else "No Answer")


root = tk.Tk()
frame = ttk.Frame(root)
frame.grid()
button = ttk.Button(frame, text="Start!", command=start)
button.grid(column=1, row=0, padx=5, pady=5)
label = ttk.Label(frame, text="No Answer")
label.grid(column=0, row=0, padx=5, pady=5)
progress_bar = ttk.Progressbar(
    frame, orient="horizontal", mode="determinate", maximum=20
)
progress_bar.grid(column=0, row=1, padx=5, pady=5)

root.mainloop()
