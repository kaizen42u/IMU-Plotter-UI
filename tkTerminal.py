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
            background="#1E1E1E",
            foreground="#CCCCCC",
            insertbackground="#CCCCCC",
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
        if "\r" in data:
            data = data.replace("\r", "")
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


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Terminal Test")
    root.geometry("900x500")

    terminal = tkTerminal(master=root, width=100)
    terminal.grid(row=0, column=0, sticky="nsew")
    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(0, weight=1)

    # Test text with ANSI colors
    terminal.write("Testing Terminal Output\n")
    terminal.write("\x1b[31mRed Text\x1b[39m\n")
    terminal.write("\x1b[32mGreen Text\x1b[39m\n")
    terminal.write("\x1b[33mYellow Text\x1b[39m\n")
    terminal.write("\x1b[34mBlue Text\x1b[39m\n")
    terminal.write("\x1b[35mMagenta Text\x1b[39m\n")
    terminal.write("\x1b[36mCyan Text\x1b[39m\n")
    terminal.write("\x1b[90mBright Black Text\x1b[39m\n")
    terminal.write("\x1b[91mBright Red Text\x1b[39m\n")
    terminal.write("\x1b[92mBright Green Text\x1b[39m\n")
    terminal.write("\x1b[93mBright Yellow Text\x1b[39m\n")
    terminal.write("\x1b[94mBright Blue Text\x1b[39m\n")
    terminal.write("\x1b[95mBright Magenta Text\x1b[39m\n")
    terminal.write("\x1b[96mBright Cyan Text\x1b[39m\n")
    terminal.write("\x1b[97mBright White Text\x1b[39m\n")
    terminal.write("\x1b[1m\x1b[32mBold Green Text\x1b[39m\x1b[21m\n")
    terminal.write("Normal text after formatting reset\n")

    root.mainloop()
