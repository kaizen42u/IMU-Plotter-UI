import tkinter as tk
from tkinter import ttk
from esp32_hw import ESP32S3, GPIO


class tkGPIOCombobox(ttk.Combobox):
    def __init__(self, master: tk.Widget, **kwargs) -> None:
        self.values = [ESP32S3.name(gpio) for gpio in ESP32S3.GPIO_PINS]
        super().__init__(master, values=self.values, state=kwargs.get("state", "readonly"), **kwargs)

    def get(self) -> GPIO | None:
        return ESP32S3.to_gpio(super().get())

    def set(self, value: GPIO | int | str) -> None:
        if isinstance(value, str):
            if value in self.values:
                super().set(value)
                return

        if isinstance(value, int):
            # This handles both int and GPIO (since GPIO is NewType based on int)
            super().set(ESP32S3.name(GPIO(value)))
            return