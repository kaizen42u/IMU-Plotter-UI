import tkinter as tk

from tkAnsiFormatter import tkAnsiFormatter


class tkTerminal:
    def __init__(
        self,
        master: tk.Misc,
        width: int = 80,
        lines: int = 200,
        autoscroll: bool = True,
    ) -> None:

        self.lines = lines
        self.autoscroll = autoscroll
        self.frame = tk.Frame(master=master)
        self.scrollbar = tk.Scrollbar(self.frame)
        self.textarea = tk.Text(
            self.frame,
            width=width,
            yscrollcommand=self.scrollbar.set,
            background="#E7FCF6",
        )

        # Place the tk.Text widget and tk.Scrollbar in the tk.Frame
        self.textarea.grid(row=0, column=0, sticky="nsew")
        self.scrollbar.grid(row=0, column=1, sticky="ns")

        # Configure the tk.Frame to expand with the window
        # self.frame.grid(row=0, column=0, sticky="nsew")
        self.frame.grid_rowconfigure(0, weight=1)
        self.frame.grid_columnconfigure(0, weight=1)

        self.ansi_formatter = tkAnsiFormatter(self.textarea)
        self.scrollbar.config(command=self.textarea.yview)

    def grid(self, **kwargs):
        self.frame.grid(**kwargs)

    # Writes text on screen
    def write(self, data: str) -> None:
        if self.ansi_formatter:
            self.ansi_formatter.insert_ansi(txt=data, index=tk.END)
        else:
            self.textarea.insert(chars=data, index=tk.END)

        # Scroll to the tk.END
        if self.autoscroll:
            self.textarea.see(index=tk.END)

        # Limit the number of lines in the terminal
        if int(self.textarea.index("end-1c").split(".")[0]) > self.lines:
            self.textarea.delete("1.0", "2.0")

    def set_autoscroll(self, autoscroll: bool) -> None:
        self.autoscroll = autoscroll
