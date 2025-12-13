import re
import tkinter as tk
from tkinter import font

# dictionaries to replace formatting code with tags
ansi_font_format = {1: "bold", 3: "italic", 4: "underline", 9: "overstrike"}
ansi_font_reset = {21: "bold", 23: "italic", 24: "underline", 29: "overstrike"}

# dictionaries to replace color code with tags
ansi_color_fg = {39: "foreground default"}
ansi_color_bg = {49: "background default"}

# Hardcoded color palettes for dark mode terminal
# Standard colors (30-37, 40-47)
DEFAULT_COLORS_DARK = [
    "#1E1E1E",        # 30: Black
    "#CD3131",        # 31: Red
    "#0DBC79",        # 32: Green
    "#E5E510",        # 33: Yellow
    "#2472C8",        # 34: Blue
    "#BC3FBC",        # 35: Magenta
    "#11A8CD",        # 36: Cyan
    "#E5E5E5",        # 37: Gray
]

# Bright colors (90-97, 100-107)
DEFAULT_COLORS_LIGHT = [
    "#E5E5E5",        # 90: Bright Gray
    "#F14C4C",        # 91: Bright Red
    "#23D18B",        # 92: Bright Green
    "#F5F543",        # 93: Bright Yellow
    "#3B8EEA",        # 94: Bright Blue
    "#D670D6",        # 95: Bright Magenta
    "#29B8DB",        # 96: Bright Cyan
    "#666666",        # 97: Bright White
]

# ANSI 8-color standard codes
ANSI_COLOR_CODES = {
    30: "Black",
    31: "Red",
    32: "Green",
    33: "Yellow",
    34: "Blue",
    35: "Magenta",
    36: "Cyan",
    37: "Gray",
    
    40: "Background Black",
    41: "Background Red",
    42: "Background Green",
    43: "Background Yellow",
    44: "Background Blue",
    45: "Background Magenta",
    46: "Background Cyan",
    47: "Background Gray",
    
    90: "Bright Gray",
    91: "Bright Red",
    92: "Bright Green",
    93: "Bright Yellow",
    94: "Bright Blue",
    95: "Bright Magenta",
    96: "Bright Cyan",
    97: "Bright White",

    100: "Background Bright Gray",
    101: "Background Bright Red",
    102: "Background Bright Green",
    103: "Background Bright Yellow",
    104: "Background Bright Blue",
    105: "Background Bright Magenta",
    106: "Background Bright Cyan",
    107: "Background Bright White",
}

# regular expression to find ansi codes in string
ansi_regexp = re.compile(r"\x1b\[((\d+;)*\d+)m")
ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class tkAnsiFormatter:
    def __init__(
        self,
        text: tk.Text,
        font: str = "Consolas",
        size: int = 9,
        colors_dark: list | None = None,
        colors_light: list | None = None,
    ) -> None:
        self.text = text
        self.font = font
        self.size = size
        self.colors_dark = colors_dark if colors_dark is not None else DEFAULT_COLORS_DARK
        self.colors_light = colors_light if colors_light is not None else DEFAULT_COLORS_LIGHT
        self.configure_style()

    @staticmethod
    def escaped(str: str) -> str:
        return ansi_escape.sub("", str)

    @staticmethod
    def get_brightness(hex_color: str) -> float:
        """Calculate brightness of a color (0-1, where 1 is brightest)."""
        hex_color = hex_color.lstrip("#")
        r, g, b = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        # Standard luminance formula
        return (0.299 * r + 0.587 * g + 0.114 * b) / 255

    @staticmethod
    def get_contrasting_text_color(bg_hex: str) -> str:
        """Return dark or white text color based on background brightness."""
        brightness = tkAnsiFormatter.get_brightness(bg_hex)
        # If background is bright, use dark text; otherwise use white text
        return "#000000" if brightness > 0.5 else "#FFFFFF"

    def configure_style(self) -> None:
        self.text.configure(font=(self.font, self.size))
        self.text.tag_configure("bold", font=(self.font, self.size, "bold"))
        self.text.tag_configure("italic", font=(self.font, self.size, "italic"))
        self.text.tag_configure("underline", underline=True)
        self.text.tag_configure("overstrike", overstrike=True)
        self.text.tag_configure("foreground default", foreground=self.text["fg"])
        self.text.tag_configure("background default", background=self.text["bg"])

        for i, (col_dark, col_light) in enumerate(
            zip(self.colors_dark, self.colors_light)
        ):
            # Foreground colors
            ansi_color_fg[30 + i] = "foreground " + col_dark
            ansi_color_fg[90 + i] = "foreground " + col_light
            self.text.tag_configure("foreground " + col_dark, foreground=col_dark)
            self.text.tag_configure("foreground " + col_light, foreground=col_light)

            # Background colors with contrasting text color for default foreground
            bg_tag_dark = "background " + col_dark
            bg_tag_light = "background " + col_light
            ansi_color_bg[40 + i] = bg_tag_dark
            ansi_color_bg[100 + i] = bg_tag_light

            # Use contrasting text color when background is applied with default foreground
            contrast_text_dark = self.get_contrasting_text_color(col_dark)
            contrast_text_light = self.get_contrasting_text_color(col_light)

            self.text.tag_configure(bg_tag_dark, background=col_dark, foreground=contrast_text_dark)
            self.text.tag_configure(bg_tag_light, background=col_light, foreground=contrast_text_light)

    def insert_ansi(self, txt: str, index: str = "insert") -> None:
        first_line, first_char = map(int, str(self.text.index(index)).split("."))

        if index == "end":
            first_line -= 1

        lines = txt.splitlines()
        if not lines:
            return

        # insert text without ansi codes
        self.text.insert(index, ansi_regexp.sub("", txt))

        # find all ansi codes in txt and apply corresponding tags
        opened_tags: dict[str, str] = {}

        # text.tag_add(tag, start, end) when we reach a "closing" ansi code
        def apply_formatting(code: int, code_index: str) -> None:
            if code == 0:  # reset all by closing all opened tag
                for tag, start in opened_tags.items():
                    self.text.tag_add(tag, start, code_index)
                opened_tags.clear()

            elif code in ansi_font_format:  # open font formatting tag
                tag = ansi_font_format[code]
                opened_tags[tag] = code_index

            elif code in ansi_font_reset:  # close font formatting tag
                tag = ansi_font_reset[code]
                if tag in opened_tags:
                    self.text.tag_add(tag, opened_tags[tag], code_index)
                    del opened_tags[tag]

            elif (
                code in ansi_color_fg
            ):  # open foreground color tag (and close previously opened one if any)
                for tag in tuple(opened_tags):
                    if tag.startswith("foreground"):
                        self.text.tag_add(tag, opened_tags[tag], code_index)
                        del opened_tags[tag]
                opened_tags[ansi_color_fg[code]] = code_index

            elif (
                code in ansi_color_bg
            ):  # open background color tag (and close previously opened one if any)
                for tag in tuple(opened_tags):
                    if tag.startswith("background"):
                        self.text.tag_add(tag, opened_tags[tag], code_index)
                        del opened_tags[tag]
                opened_tags[ansi_color_bg[code]] = code_index

        def find_ansi(line_txt: str, line_nb: int, char_offset: int) -> None:
            # difference between the character position in the original line and in the text widget
            # (initial offset due to insertion position if first line + extra offset due to deletion of ansi codes)
            delta = -char_offset

            for match in ansi_regexp.finditer(line_txt):
                codes = [int(c) for c in match.groups()[0].split(";")]
                start, end = match.span()
                for code in codes:
                    apply_formatting(code, "{}.{}".format(line_nb, start - delta))

                # take into account offset due to deletion of ansi code
                delta += end - start

        # first line, with initial offset due to insertion position
        find_ansi(lines[0], first_line, first_char)

        for line_nb, line in enumerate(lines[1:], first_line + 1):
            find_ansi(line, line_nb, 0)  # next lines, no offset

        # close still opened tag
        for tag, start in opened_tags.items():
            self.text.tag_add(tag, start, "end")


if __name__ == "__main__":

    # example for the kind of output you can get with "ls --color"
    output = "file.pdf\nfile.txt\n\x1b[0m\x1b[01;34mfolder\x1b[0m\n\x1b[01;32mscript.py\x1b[0m\ntest\n"

    root = tk.Tk()
    terminal = tk.Text(root, width=160)
    terminal.pack()
    formatter = tkAnsiFormatter(terminal)
    formatter.insert_ansi(output, "end")

    print(font.families())
    root.mainloop()
