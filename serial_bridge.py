"""Qt signal bridge for serialHandler — routes background-thread callbacks to the main thread."""

from PySide6.QtCore import QObject, Signal


class SerialBridge(QObject):
    """Converts serialHandler callbacks into Qt signals.

    Qt automatically queues cross-thread signal emissions to the receiver's thread,
    so all connected slots run safely in the main thread without manual locking.
    """

    line_received = Signal(str)
    line_sent = Signal(str)
    log_message = Signal(str)
    ports_changed = Signal(list)
    disconnected = Signal(str)

    def __init__(self, serial_handler) -> None:
        super().__init__()
        serial_handler.set_line_received_callback(self.line_received.emit)
        serial_handler.set_line_send_callback(self.line_sent.emit)
        serial_handler.set_log_callback(self.log_message.emit)
        serial_handler.set_ports_changed_callback(self.ports_changed.emit)
        serial_handler.set_disconnect_callback(self.disconnected.emit)
