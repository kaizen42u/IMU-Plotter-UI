import os
import threading
import serial
import serial.tools.list_ports
from time import sleep
from typing import Callable, Optional, List


class SerialHandler:
    def __init__(
        self,
        line_received: Optional[Callable[[str], None]] = None,
        log: Optional[Callable[[str], None]] = None,
        ports_changed: Optional[Callable[[List[str]], None]] = None,
    ):
        self.serial_port: Optional[serial.Serial] = None
        self.killed: bool = False
        self.line_received: Optional[Callable[[str], None]] = line_received
        self.log: Optional[Callable[[str], None]] = log
        self.ports_changed: Optional[Callable[[List[str]], None]] = ports_changed
        self.current_ports: List[str] = self.get_ports()
        self.port_monitor_thread = threading.Thread(target=self.monitor_ports)
        self.port_monitor_thread.start()

    def get_ports(self) -> List[str]:
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def connect(self, port: str, baudrate: int = 115200) -> None:
        self.serial_port = serial.Serial(port)
        self.serial_port.close()
        self.serial_port = serial.Serial(port, baudrate=baudrate, timeout=1.0)
        if self.log:
            self.log(f"Port [{self.serial_port.name}] Connected\n")

    def disconnect(self) -> None:
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
            if self.log:
                self.log(f"Port [{self.serial_port.name}] Disconnected\n")

    def read_from_port(self) -> None:
        try:
            while not self.killed:
                sleep(0.05)
                while self.serial_port and self.serial_port.is_open:
                    try:
                        line = self.serial_port.readline()
                        if not line:
                            break
                        reading = line.decode("utf-8")
                        if self.line_received:
                            self.line_received(reading)
                    except serial.SerialException as serr:
                        self.disconnect()
                        if self.log:
                            self.log(
                                f"Could not read port [{self.serial_port.port}]: {serr}"
                            )
                    except TypeError as terr:
                        if self.log:
                            self.log(
                                f"Bad serial data for port [{self.serial_port.port}]: {terr}"
                            )
                    except Exception as err:
                        if self.log:
                            self.log(f"Serial Exception: {err}")
            print("Serial Port thread exiting")
        except Exception as err:
            if self.log:
                self.log(f"### Serial Port thread killed, trying to restart: {err} ###")
            self.read_serial_thread = threading.Thread(target=self.read_from_port)
            self.read_serial_thread.start()

    def close(self) -> None:
        self.killed = True
        self.disconnect()
        self.read_serial_thread.join(timeout=1)
        if self.read_serial_thread.is_alive():
            print("read_serial_thread did not exit in time")
        print("[W] Close terminal to exit the program.")
        self.port_monitor_thread.join(timeout=1)
        if self.port_monitor_thread.is_alive():
            print("port_monitor_thread did not exit in time")

    def set_line_received_callback(self, callback: Callable[[str], None]) -> None:
        self.line_received = callback

    def set_log_callback(self, callback: Callable[[str], None]) -> None:
        self.log = callback

    def set_ports_changed_callback(self, callback: Callable[[List[str]], None]) -> None:
        self.ports_changed = callback

    def monitor_ports(self) -> None:
        while not self.killed:
            sleep(1)
            new_ports = self.get_ports()
            if new_ports != self.current_ports:
                self.current_ports = new_ports
                if self.ports_changed:
                    self.ports_changed(new_ports)


# Test code
def my_line_received(line: str) -> None:
    print(f"Received: {line}")


def my_log(message: str) -> None:
    print(f"Log: {message}")


def my_ports_changed(ports: List[str]) -> None:
    print(f"Ports changed: {ports}")


if __name__ == "__main__":
    serial_handler = SerialHandler()
    serial_handler.set_line_received_callback(my_line_received)
    serial_handler.set_log_callback(my_log)
    serial_handler.set_ports_changed_callback(my_ports_changed)

    ports = serial_handler.get_ports()
    if ports:
        serial_handler.connect(ports[0])
        read_thread = threading.Thread(target=serial_handler.read_from_port)
        read_thread.start()

        try:
            while True:
                sleep(1)
        except KeyboardInterrupt:
            serial_handler.close()
            read_thread.join()
    else:
        print("No serial ports found.")
