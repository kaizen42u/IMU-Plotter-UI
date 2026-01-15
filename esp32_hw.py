"""ESP32 hardware configuration and definitions."""

from typing import NewType

# GPIO type - represents a GPIO pin number
GPIO = NewType("GPIO", int)


class ESP32S3:
    """ESP32-S3 hardware specifications and GPIO definitions."""

    # ESP32-S3 has GPIO 0-21, 26-48 available for general use
    GPIO_PINS: list[GPIO] = [GPIO(i) for i in range(22)] + [
        GPIO(i) for i in range(26, 49)
    ]

    # Special pins with warnings about their intended usage
    SPECIAL_PINS: dict[GPIO, str] = {
        GPIO(0): "Strapping pin - Boot mode selection (pull-up recommended)",
        GPIO(3): "Strapping pin - JTAG enable (floating/pull-up recommended)",
        GPIO(19): "USB D- - USB OTG peripheral",
        GPIO(20): "USB D+ - USB OTG peripheral",
        GPIO(43): "TX - UART0 debug output (ROM bootloader)",
        GPIO(44): "RX - UART0 debug input (ROM bootloader)",
        GPIO(45): "Strapping pin - VDD_SPI voltage selection",
        GPIO(46): "Strapping pin - ROM message printing control",
        GPIO(26): "SPICS1 - Connected to flash/PSRAM",
        GPIO(27): "SPIHD - Connected to flash/PSRAM (quad mode)",
        GPIO(28): "SPIWP - Connected to flash/PSRAM (quad mode)",
        GPIO(29): "SPICS0 - Connected to flash/PSRAM",
        GPIO(30): "SPICLK - Connected to flash/PSRAM",
        GPIO(31): "SPIQ - Connected to flash/PSRAM",
        GPIO(32): "SPID - Connected to flash/PSRAM",
        GPIO(33): "SPIIO4 - Connected to octal flash/PSRAM",
        GPIO(34): "SPIIO5 - Connected to octal flash/PSRAM",
        GPIO(35): "SPIIO6 - Connected to octal flash/PSRAM",
        GPIO(36): "SPIIO7 - Connected to octal flash/PSRAM",
        GPIO(37): "SPIDQS - Connected to octal flash/PSRAM",
    }

    @classmethod
    def is_special_pin(cls, gpio: GPIO) -> bool:
        """Check if a GPIO pin has special functions."""
        return gpio in cls.SPECIAL_PINS

    @classmethod
    def get_pin_warning(cls, gpio: GPIO) -> str | None:
        """Get warning message for special GPIO pins."""
        return cls.SPECIAL_PINS.get(gpio)

    @classmethod
    def is_valid_gpio(cls, gpio_num: GPIO) -> bool:
        """Check if a GPIO number is valid on ESP32."""
        return gpio_num in cls.GPIO_PINS

    @classmethod
    def name(cls, gpio_num: GPIO) -> str:
        if isinstance(gpio_num, int):
            gpio_num = GPIO(gpio_num)
            return f"GPIO{gpio_num}"
        return "Unknown GPIO"
    
    @classmethod
    def to_gpio(cls, gpio_str: str) -> GPIO | None:
        """Convert a string like 'GPIO12' to GPIO type."""
        if gpio_str.startswith("GPIO"):
            try:
                num = int(gpio_str[4:])
                gpio = GPIO(num)
                if cls.is_valid_gpio(gpio):
                    return gpio
            except ValueError:
                return None
        return None