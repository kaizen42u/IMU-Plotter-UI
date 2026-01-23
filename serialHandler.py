import threading
import serial
import serial.tools.list_ports
from time import sleep
from typing import Callable, List


class serialHandler:
    def __init__(
        self,
        baudrate: int = 115200,
        timeout: float = 0.1,
    ):
        # Initialize thread-safe locks first
        self._lock = threading.RLock()
        self._killed_event = threading.Event()

        self.serial_port: serial.Serial | None = None
        self.connected_port: str | None = (
            None  # Track the connected port for disconnect callback
        )
        self.killed: bool = False
        self.line_received_callback: Callable[[str], None] | None = None
        self.line_send_callback: Callable[[str], None] | None = None
        self.log_callback: Callable[[str], None] | None = None
        self.ports_changed_callback: Callable[[List[str]], None] | None = None
        self.disconnect_callback: Callable[[str], None] | None = None
        self.current_ports: List[str] = self.get_ports()
        self.read_serial_thread: threading.Thread | None = None
        self.baudrate: int = baudrate
        self.timeout: float = timeout

        # Start threads after all attributes are initialized
        self.port_monitor_thread = threading.Thread(
            target=self.monitor_ports, daemon=True
        )
        self.port_monitor_thread.start()

    def log(self, message: str) -> None:
        if self.log_callback:
            self.log_callback(message)

    def get_ports(self) -> List[str]:
        ports = serial.tools.list_ports.comports()
        return [port.device for port in ports]

    def connect(self, port: str, baudrate: int | None = None) -> bool:
        with self._lock:
            if self.is_connected():
                self.log("Already connected. Disconnect first.")
                return False
            if baudrate is None:
                baudrate = self.baudrate
            try:
                self.serial_port = serial.Serial(
                    port, baudrate=baudrate, timeout=self.timeout
                )
                self.connected_port = port
                self._killed_event.clear()
                self.log(f"Port [{self.serial_port.name}] Connected")
                self.read_serial_thread = threading.Thread(
                    target=self.read_from_port, daemon=True
                )
                self.read_serial_thread.start()
                return True
            except serial.SerialException as err:
                self.log(f"Failed to connect to port [{port}]: {err}")
                return False

    def disconnect(self) -> None:
        with self._lock:
            if self.serial_port and self.serial_port.is_open:
                try:
                    port_name = self.serial_port.name
                    self.serial_port.close()
                    if not self.serial_port.is_open:
                        self.log(f"Port [{port_name}] Disconnected")
                    else:
                        self.log(f"Failed to close port [{port_name}]")
                except Exception as err:
                    self.log(f"Error closing port: {err}")
                finally:
                    self.serial_port = None
                    self.connected_port = None

    def is_connected(self) -> bool:
        return self.serial_port is not None and self.serial_port.is_open

    def send(self, data: str) -> bool:
        """Send data to the serial port. Returns True if successful, False otherwise."""
        with self._lock:
            if not self.is_connected() or self.serial_port is None:
                self.log("Cannot send data: port is not connected")
                return False
            try:
                self.serial_port.write(data.encode("utf-8"))
                self.serial_port.flush()  # Flush immediately to avoid buffering delays
                # Call line_send_callback if provided
                if self.line_send_callback:
                    self.line_send_callback(data)
                return True
            except serial.SerialException as err:
                self.log(f"Failed to send data: {err}")
                self.disconnect()
                return False
            except Exception as err:
                self.log(f"Error sending data: {err}")
                return False

    def read_from_port(self) -> None:
        try:
            while not self._killed_event.is_set():
                line = None
                with self._lock:
                    if not self.is_connected() or self.serial_port is None:
                        break
                    try:
                        line = self.serial_port.readline()
                    except serial.SerialException as err:
                        self.log(f"Serial port error: {err}")
                        break
                    except Exception as err:
                        self.log(f"Unexpected error reading from port: {err}")
                        break

                if line:
                    try:
                        reading = line.decode("utf-8").rstrip("\n")
                        if self.line_received_callback:
                            self.line_received_callback(reading)
                    except UnicodeDecodeError as err:
                        self.log(f"Bad serial data: {err}")
                else:
                    sleep(self.timeout)
            print("Serial port read thread exiting")
        except Exception as err:
            self.log(f"Fatal error in read thread: {err}")

    def close(self) -> None:
        self._killed_event.set()
        self.disconnect()

        if self.read_serial_thread and self.read_serial_thread.is_alive():
            self.read_serial_thread.join(timeout=2)
            if self.read_serial_thread.is_alive():
                self.log("Warning: read_serial_thread did not exit in time")

        if self.port_monitor_thread.is_alive():
            self.port_monitor_thread.join(timeout=2)
            if self.port_monitor_thread.is_alive():
                self.log("Warning: port_monitor_thread did not exit in time")

    def set_line_received_callback(self, callback: Callable[[str], None]) -> None:
        self.line_received_callback = callback

    def set_line_send_callback(self, callback: Callable[[str], None]) -> None:
        self.line_send_callback = callback

    def set_log_callback(self, callback: Callable[[str], None]) -> None:
        self.log_callback = callback

    def set_ports_changed_callback(self, callback: Callable[[List[str]], None]) -> None:
        self.ports_changed_callback = callback

    def set_disconnect_callback(self, callback: Callable[[str], None] | None) -> None:
        self.disconnect_callback = callback

    def monitor_ports(self) -> None:
        while not self._killed_event.is_set():
            sleep(1)
            new_ports = self.get_ports()
            callback = None
            port_disconnected = False
            disconnected_port: str | None = None

            with self._lock:
                if new_ports != self.current_ports:
                    self.current_ports = new_ports
                    callback = self.ports_changed_callback

                # Check if the connected port is no longer available
                if self.connected_port and self.connected_port not in new_ports:
                    port_disconnected = True
                    disconnected_port = self.connected_port

            # Disconnect if port became unavailable
            if port_disconnected and disconnected_port:
                self.disconnect()

                print(
                    f"Auto-disconnected from port [{disconnected_port}] (no longer available)"
                )
                if self.disconnect_callback:
                    self.disconnect_callback(disconnected_port)

            if callback:
                callback(new_ports)


# Test code
def my_line_received(line: str) -> None:
    print(f"Received: {line}")


def my_log(message: str) -> None:
    print(f"Log: {message}")


def my_ports_changed(ports: List[str]) -> None:
    print(f"Ports changed: {ports}")


if __name__ == "__main__":
    serial_handler = serialHandler()
    serial_handler.set_line_received_callback(my_line_received)
    serial_handler.set_log_callback(my_log)
    serial_handler.set_ports_changed_callback(my_ports_changed)

    ports = serial_handler.get_ports()
    if ports:
        serial_handler.connect(ports[0])
        try:
            while True:
                serial_handler.send("Hello World!\n")
                sleep(1)
        except KeyboardInterrupt:
            print("Exiting...")
            serial_handler.close()
            exit()
    else:
        print("No serial ports found.")
