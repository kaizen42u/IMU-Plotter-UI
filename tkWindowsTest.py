import tkinter as tk


class tkWindow(tk.Toplevel):
    def __init__(
        self, master: tk.Misc, control: tk.Button, name: str | None = None, **args
    ) -> None:
        super().__init__(master, **args)
        self.master = master
        self.control = control
        self.name = name

        self.control.configure(command=self.toggle_window)

        # Bind the child window close event to the handler
        self.protocol("WM_DELETE_WINDOW", self.hide_window)

        self.toggle_window()

    # Function to toggle the child window
    def toggle_window(self) -> None:
        self.hide_window() if self.winfo_viewable() else self.show_window()

    def hide_window(self) -> None:
        self.withdraw()
        self.control.configure(text=f"Show {self.name}" if self.name else "Show")

    def show_window(self) -> None:
        self.deiconify()
        self.control.configure(text=f"Hide {self.name}" if self.name else "Hide")


def main():

    # Function to update the label in the parent window
    def update_label(*args):
        label_var.set(entry_var.get())

    # Primary tkinter window
    parent = tk.Tk()
    parent.title("Parent")

    # Label in the parent window
    label_var = tk.StringVar()
    label = tk.Label(parent, textvariable=label_var)
    label.pack(pady=20)

    # Button to open/close the child window
    toggle_button = tk.Button(parent)
    toggle_button.pack(pady=10)

    # A child window can be created like so
    child = tkWindow(parent, toggle_button, "Child")
    child.title("Child")

    # Entry in the child window
    entry_var = tk.StringVar()
    entry = tk.Entry(child, textvariable=entry_var)
    entry.pack(pady=20)

    # Bind the StringVar to the update function
    entry_var.trace_add("write", update_label)

    parent.mainloop()


if __name__ == "__main__":
    main()
