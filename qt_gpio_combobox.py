"""GPIO pin selector combobox for ESP32-S3 (replaces tkGPIOCombobox)."""

from PySide6.QtWidgets import QComboBox
from esp32_hw import ESP32S3, GPIO


class QtGPIOCombobox(QComboBox):
    """Combobox pre-populated with all valid ESP32-S3 GPIO names."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._names = [ESP32S3.get_gpio_name(g) for g in ESP32S3.AVAILABLE_GPIO_PINS]
        self.addItems(self._names)

    def get_gpio(self) -> GPIO | None:
        return ESP32S3.get_gpio_from_name_str(self.currentText())

    def set_gpio(self, value: GPIO | int | str) -> None:
        if isinstance(value, str):
            idx = self.findText(value)
            if idx >= 0:
                self.setCurrentIndex(idx)
                return
            # Maybe it's a bare number string
            if value.isdigit():
                value = int(value)
        if isinstance(value, int):
            name = ESP32S3.get_gpio_name(GPIO(value))
            idx = self.findText(name)
            if idx >= 0:
                self.setCurrentIndex(idx)
