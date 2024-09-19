import threading
import serial
import serial.tools.list_ports
from time import sleep
from typing import Callable, Optional, List


class SerialHandler:
    def __init__(
        self,
        line_received_callback: Optional[Callable[[str], None]] = None,
        log_callback: Optional[Callable[[str], None]] = None,
        ports_changed_callback: Optional[Callable[[List[str]], None]] = None,
        interval: float = 0.05,
    ):
        self.serial_port: Optional[serial.Serial] = None
        self.killed: bool = False
        self.line_received_callback: Optional[Callable[[str], None]] = (
            line_received_callback
        )
        self.log_callback: Optional[Callable[[str], None]] = log_callback
        self.ports_changed_callback: Optional[Callable[[List[str]], None]] = (
            ports_changed_callback
        )
        self.current_ports: List[str] = self.get_ports()
        self.port_monitor_thread = threading.Thread(target=self.monitor_ports)
        self.port_monitor_thread.start()
        self.read_serial_thread: Optional[threading.Thread] = None
        self.interval = interval

    def log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(message)

    def get_ports(self) -> List[str]:
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def connect(self, port: str, baudrate: int = 115200) -> None:
        self.serial_port = serial.Serial(port)
        self.serial_port.close()
        self.serial_port = serial.Serial(port, baudrate=baudrate, timeout=1.0)
        if self.log:
            self.log(f"Port [{self.serial_port.name}] Connected")

        self.read_thread = threading.Thread(target=self.read_from_port)
        self.read_thread.start()

    def disconnect(self) -> None:
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            if not self.serial_port.is_open:
                self.log(f"Port [{self.serial_port.name}] Disconnected")
                # self.read_thread.join()
            else:
                self.log(f"Failed to close port [{self.serial_port.name}]")

    def is_connected(self) -> bool:
        return self.serial_port is not None and self.serial_port.is_open

    def read_from_port(self) -> None:
        try:
            while not self.killed and self.is_connected():
                sleep(self.interval)
                line: bytes | None = b"empty"
                while self.is_connected() and line:
                    try:
                        if self.serial_port is not None:
                            line = self.serial_port.readline()
                            if not line:
                                break
                            reading = line.decode("utf-8").rstrip("\n")
                            if self.line_received_callback:
                                self.line_received_callback(reading)
                    except serial.SerialException as serr:
                        self.disconnect()
                        self.log(
                            f"Could not read port [{self.serial_port.name if self.serial_port else None}]: {serr}"
                        )
                    except TypeError as terr:
                        self.log(
                            f"Bad serial data for port [{self.serial_port.name if self.serial_port else None}]: {terr}"
                        )
                    except Exception as err:
                        self.log(f"Serial Exception: {err}")
            print("Serial Port thread exiting")
        except Exception as err:
            self.log(f"### Serial Port thread killed, trying to restart: {err} ###")
            self.read_serial_thread = threading.Thread(target=self.read_from_port)
            self.read_serial_thread.start()

    def close(self) -> None:
        self.killed = True
        self.disconnect()
        if self.read_serial_thread:
            if self.read_serial_thread.is_alive():
                self.read_serial_thread.join(timeout=1)
            if self.read_serial_thread.is_alive():
                print("read_serial_thread did not exit in time")
        self.port_monitor_thread.join(timeout=1)
        if self.port_monitor_thread.is_alive():
            print("port_monitor_thread did not exit in time")

    def set_line_received_callback(self, callback: Callable[[str], None]) -> None:
        self.line_received_callback = callback

    def set_log_callback(self, callback: Callable[[str], None]) -> None:
        self.log_callback = callback

    def set_ports_changed_callback(self, callback: Callable[[List[str]], None]) -> None:
        self.ports_changed_callback = callback

    def monitor_ports(self) -> None:
        while not self.killed:
            sleep(1)
            new_ports = self.get_ports()
            if new_ports != self.current_ports:
                self.current_ports = new_ports
                if self.ports_changed_callback:
                    self.ports_changed_callback(new_ports)


# Test code
def my_line_received(line: str) -> None:
    print(f"Received: {line}")


def my_log(message: str) -> None:
    print(f"Log: {message}")


def my_ports_changed(ports: Optional[List[str]]) -> None:
    print(f"Ports changed: {ports}")


if __name__ == "__main__":
    serial_handler = SerialHandler()
    serial_handler.set_line_received_callback(my_line_received)
    serial_handler.set_log_callback(my_log)
    serial_handler.set_ports_changed_callback(my_ports_changed)

    ports = serial_handler.get_ports()
    if ports:
        serial_handler.connect(ports[0])
        try:
            while True:
                sleep(1)
        except KeyboardInterrupt:
            print("Exiting...")
            serial_handler.close()
            exit()
    else:
        print("No serial ports found.")
