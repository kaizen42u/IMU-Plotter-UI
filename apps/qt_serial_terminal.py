"""Qt serial terminal widget (replaces apps/serialTerminal.py)."""

import re
import threading
from datetime import datetime
from pathlib import Path
from queue import Queue
from typing import Callable, List

DEBUG = True  # set False for release builds

from PySide6.QtCore import QTimer, Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QLineEdit,
)

from configManager import get_active_config_path, list_config_profiles
from config_store import pool, switch_profile
from qt_terminal import AnsiTerminal, _best_mono_font
from serial_bridge import SerialBridge
from serialHandler import serialHandler

# Matches proper ANSI escapes (\x1b[...X) and bare-bracket SGR codes ([digits m]).
# The bare-bracket form requires at least one digit so that [EVENT / [ABC etc. are NOT stripped.
_ANSI_STRIP = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\[[0-9;]+m")


def _strip_ansi(text: str) -> str:
    return _ANSI_STRIP.sub("", text)


class SerialTerminalWidget(QWidget):
    """Central serial communication panel.

    Provides the same API surface as the old SerialTerminal (register_event_callback,
    register_connection_state_callback, send_command, etc.) so existing app code
    requires minimal changes.
    """

    # Signals consumed by app panels
    connection_changed = Signal(bool)  # True = connected

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._cfg = pool.section("serial", defaults={
            "port": "/dev/ttyUSB0",
            "baudrate": 115200,
            "auto_scroll": True,
            "logging_enabled": True,
            "terminal_max_width": 500,
            "auto_reconnect": False,
            "auto_connect": False,
            "show_events": True,
            "local_echo": True,
            "bytesize": "8",
            "parity": "None",
            "stopbits": "1",
            "flow_control": "None",
        })
        self._port: str = self._cfg.port
        self._baudrate: int = self._cfg.baudrate
        self._auto_scroll: bool = self._cfg.auto_scroll
        self._logging_default: bool = self._cfg.logging_enabled

        self._reconnect_enabled: bool = self._cfg.auto_reconnect
        self._reconnect_port: str = ""   # remembered across port disappear/reappear cycles
        self._reconnect_attempts = 0
        self._reconnect_timer: QTimer | None = None  # debounce timer
        self._show_events: bool = self._cfg.show_events
        # Local echo of sent commands ("> cmd", shown purple). Redundant now that
        # the firmware echoes commands itself, so it's toggleable.
        self._show_echo: bool = self._cfg.local_echo

        # Callbacks (legacy API)
        self._connection_callbacks: List[Callable[[], None]] = []
        self._line_received_callbacks: List[Callable[[str], None]] = []
        self._event_callbacks: dict[str, List[Callable[[str, str], None]]] = {}
        self._pending_event_enables: set[str] = set()
        # Fires after every successful send_command() call regardless of source.
        # callback(cmd: str) — cmd is stripped of trailing "\n" and whitespace.
        self._send_callbacks: List[Callable[[str], None]] = []

        # Command history
        self._history: List[str] = []
        self._history_index = -1
        self._history_temp = ""

        # Logging
        self._logging_enabled = False
        self._log_file = None
        self._log_queue: Queue = Queue()
        self._log_thread: threading.Thread | None = None

        # Serial handler + bridge
        self.serial = serialHandler()
        self._bridge = SerialBridge(self.serial)
        self._bridge.line_received.connect(self._on_line_received)
        self._bridge.log_message.connect(self._on_log_message)
        self._bridge.ports_changed.connect(self._on_ports_changed)
        self._bridge.disconnected.connect(self._on_disconnected)

        self._build_ui()
        self._load_profiles()

        # Block signals so setChecked doesn't fire toggled (the signal is already connected).
        # Then start logging manually once if needed.
        self._logging_checkbox.blockSignals(True)
        self._logging_checkbox.setChecked(self._logging_default)
        self._logging_checkbox.blockSignals(False)
        if self._logging_default:
            self._start_logging()

        ports = self.serial.get_ports()
        self._port_combo.addItems(ports)
        if self._port in ports:
            self._port_combo.setCurrentText(self._port)

        self._update_connect_button()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # These widgets are controlled via the menu bar / COM Port window.
        # They must exist for internal methods to reference, but are kept hidden.
        def _hidden(w):
            w.hide()
            return w

        self._port_combo = _hidden(QComboBox(self))
        self._port_combo.setEditable(True)

        self._baud_combo = _hidden(QComboBox(self))
        self._baud_combo.addItems(
            ["9600", "14400", "19200", "38400", "57600",
             "115200", "230400", "460800", "921600"]
        )
        self._baud_combo.setCurrentText(str(self._baudrate))
        self._baud_combo.setEditable(True)

        self._connect_btn = _hidden(QPushButton("Connect", self))
        self._connect_btn.clicked.connect(self._toggle_connection)

        self._autoscroll_cb = _hidden(QCheckBox("Auto Scroll", self))
        self._autoscroll_cb.setChecked(self._auto_scroll)
        self._autoscroll_cb.toggled.connect(self._on_autoscroll_toggled)

        self._logging_checkbox = _hidden(QCheckBox("Logging", self))
        self._logging_checkbox.toggled.connect(self._on_logging_toggled)

        self._profile_combo = _hidden(QComboBox(self))
        self._profile_combo.currentTextChanged.connect(self._on_profile_selected)

        # --- Terminal ---
        self._terminal = AnsiTerminal(max_lines=self._cfg.terminal_max_width, autoscroll=self._auto_scroll)
        self._terminal.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        root.addWidget(self._terminal, stretch=1)

        # --- Send command row ---
        row_send = QHBoxLayout()
        self._cmd_entry = QLineEdit()
        self._cmd_entry.setFont(_best_mono_font(11))
        self._cmd_entry.setPlaceholderText("type here or click the terminal and start typing…")
        self._cmd_entry.setStyleSheet("""
            QLineEdit {
                background-color: #1E1E1E;
                color: #D4D4D4;
                border: 1px solid #3C3C3C;
                border-top: none;
                padding: 4px 6px;
                selection-background-color: #264F78;
                selection-color: #FFFFFF;
            }
        """)
        self._cmd_entry.returnPressed.connect(self._send_from_ui)
        self._cmd_entry.installEventFilter(self)
        row_send.addWidget(self._cmd_entry, stretch=1)
        self._terminal.installEventFilter(self)
        send_btn = QPushButton("Send")
        send_btn.clicked.connect(self._send_from_ui)
        row_send.addWidget(send_btn)
        root.addLayout(row_send)

    def eventFilter(self, obj, event):
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        if event.type() != QEvent.Type.KeyPress:
            return super().eventFilter(obj, event)

        key = event.key()

        if obj is self._cmd_entry:
            if key == Qt.Key.Key_Up:
                self._history_prev()
                return True
            if key == Qt.Key.Key_Down:
                self._history_next()
                return True

        elif obj is self._terminal:
            # Ctrl+key combinations stay with the terminal (copy, scroll, etc.)
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                return False
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self._send_from_ui()
                return True
            if key == Qt.Key.Key_Backspace:
                self._cmd_entry.backspace()
                self._cmd_entry.setFocus()
                return True
            if key == Qt.Key.Key_Escape:
                self._cmd_entry.clear()
                return True
            if event.text():
                self._cmd_entry.setFocus()
                QApplication.sendEvent(self._cmd_entry, event)
                return True

        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Profile management
    # ------------------------------------------------------------------

    def _load_profiles(self) -> None:
        self._profile_paths: dict[str, Path] = list_config_profiles()
        self._profile_combo.blockSignals(True)
        self._profile_combo.clear()
        self._profile_combo.addItems(list(self._profile_paths.keys()))

        active = get_active_config_path()
        for name, path in self._profile_paths.items():
            try:
                if path.resolve() == active.resolve():
                    self._profile_combo.setCurrentText(name)
                    break
            except Exception:
                pass
        self._profile_combo.blockSignals(False)

    def _on_profile_selected(self, name: str) -> None:
        path = self._profile_paths.get(name)
        if not path:
            return
        switch_profile(path)
        # self._cfg is now rebound to the new profile's data
        self._port = self._cfg.port or self._port
        self._baudrate = self._cfg.baudrate or self._baudrate
        self._port_combo.setCurrentText(self._port)
        self._baud_combo.setCurrentText(str(self._baudrate))
        self.show_message(f"\x1b[32mConfig profile set to {name}\x1b[0m")

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def _on_logging_toggled(self, checked: bool) -> None:
        if checked:
            self._start_logging()
        else:
            self._stop_logging()

    def _start_logging(self) -> None:
        try:
            log_dir = Path("./session_logs")
            log_dir.mkdir(exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_path = log_dir / f"{ts}.log"
            self._log_file = open(log_path, "w")
            self._logging_enabled = True
            self._log_thread = threading.Thread(target=self._log_writer, daemon=True)
            self._log_thread.start()
            self.show_message(f"\x1b[32mLogging started: {log_path}\x1b[0m")
        except Exception as e:
            self.show_message(f"\x1b[31mFailed to start logging: {e}\x1b[0m")
            self._logging_checkbox.setChecked(False)

    def _stop_logging(self) -> None:
        if self._logging_enabled:
            self._logging_enabled = False
            self._log_queue.put(None)
            if self._log_thread and self._log_thread.is_alive():
                self._log_thread.join(timeout=2)
        if self._log_file:
            self._log_file.close()
            self._log_file = None
        self.show_message("\x1b[32mLogging stopped\x1b[0m")

    def _log_writer(self) -> None:
        while True:
            item = self._log_queue.get(timeout=None)
            if item is None:
                break
            try:
                if self._log_file:
                    self._log_file.write(item)
                    self._log_file.flush()
            except Exception:
                pass

    def _write_log(self, direction: str, data: str) -> None:
        if not self._logging_enabled:
            return
        now = datetime.now()
        ts = now.strftime("%y%m%d-%H%M%S")
        ms = now.microsecond // 1000
        clean = data.rstrip("\n\r")
        self._log_queue.put(f"({ts}.{ms:03d})({direction}) | {clean}\n")

    # ------------------------------------------------------------------
    # Serial connection
    # ------------------------------------------------------------------

    def _toggle_connection(self) -> None:
        if self.serial.is_connected():
            self.disconnect_from()
            return
        try:
            port = self._port_combo.currentText()
            baud = int(self._baud_combo.currentText())
            self.connect_to(port, baud)
        except ValueError:
            self.show_message("\x1b[31mInvalid baudrate\x1b[0m")

    # Public API used by COMPortWindow (and callable from scripts / tests).

    def connect_to(self, port: str, baud: int, **serial_kwargs) -> bool:
        """Connect to *port* at *baud*.  Updates the widget UI.  Returns success."""
        try:
            if not self.serial.connect(port, baudrate=baud, **serial_kwargs):
                return False
            self._reconnect_enabled = True
            self._reconnect_port = port
            self._reconnect_attempts = 0
            # Keep the widget combos in sync so they reflect what we're connected to.
            self._port_combo.setCurrentText(port)
            self._baud_combo.setCurrentText(str(baud))
            self._update_connect_button()
            QTimer.singleShot(150, self._sync_repl)
            return True
        except Exception as e:
            self.show_message(f"\x1b[31mConnect failed: {e}\x1b[0m")
            return False

    def disconnect_from(self) -> None:
        """Disconnect and disable auto-reconnect."""
        self.serial.disconnect()
        self._reconnect_enabled = False
        self._reconnect_port = ""
        self._cancel_reconnect_timer()
        self._update_connect_button()

    def connect_from_settings(self) -> None:
        """Connect using the port/baud stored in the hidden combo widgets."""
        try:
            port = self._port_combo.currentText()
            baud = int(self._baud_combo.currentText())
            self.connect_to(port, baud)
        except ValueError:
            self.show_message("\x1b[31mInvalid baudrate\x1b[0m")

    def try_auto_connect(self) -> None:
        """Connect on startup if auto_connect is enabled and the port is available."""
        if not self._cfg.auto_connect:
            return
        if self.serial.is_connected():
            return
        port = self._port_combo.currentText()
        if port and port in self.serial.get_ports():
            self.connect_from_settings()

    def _sync_repl(self) -> None:
        """Send a bare newline so the device REPL emits a clean prompt."""
        if self.serial.is_connected():
            self.serial.send("\r\n")

    def _update_connect_button(self) -> None:
        connected = self.serial.is_connected()
        self._connect_btn.setText("Disconnect" if connected else "Connect")
        self._port_combo.setEnabled(not connected)
        self._baud_combo.setEnabled(not connected)
        self._notify_connection_changed()

    def _notify_connection_changed(self) -> None:
        connected = self.serial.is_connected()
        if connected and self._pending_event_enables:
            self._send_pending_events()
        self.connection_changed.emit(connected)
        for cb in self._connection_callbacks:
            try:
                cb()
            except Exception as e:
                if DEBUG:
                    print(f"[DEBUG][ERROR] connection callback: {e}")

    def _on_disconnected(self, port: str) -> None:
        self._update_connect_button()
        # If the port is still present it was a comm error (not physical removal) — try once.
        # Physical-removal reconnect is handled by _on_ports_changed when the port reappears.
        if self._reconnect_enabled and port in self.serial.get_ports():
            self._schedule_reconnect()

    def _on_ports_changed(self, ports: list[str]) -> None:
        connected = self.serial.is_connected()

        if not connected:
            # Rebuild the combobox to exactly match available ports (removes stale entries).
            self._port_combo.blockSignals(True)
            old_items = [self._port_combo.itemText(i) for i in range(self._port_combo.count())]
            self._port_combo.clear()
            self._port_combo.addItems(ports)
            # Prefer the reconnect target; fall back to first available.
            if self._reconnect_port in ports:
                self._port_combo.setCurrentText(self._reconnect_port)
            elif ports:
                self._port_combo.setCurrentIndex(0)
            self._port_combo.blockSignals(False)

            # Log insertions and removals to the terminal.
            added = [p for p in ports if p not in old_items]
            removed = [p for p in old_items if p not in ports]
            for p in added:
                self.show_message(f"[PORT] Device attached: {p}")
                if DEBUG:
                    print(f"[DEBUG][PORT] attached: {p}")
            for p in removed:
                self.show_message(f"[PORT] Device removed: {p}")
                if DEBUG:
                    print(f"[DEBUG][PORT] removed: {p}")
            if ports and DEBUG:
                print(f"[DEBUG][PORT] available: {ports}")

        # When the target port reappears, schedule a debounced reconnect.
        if self._reconnect_enabled and self._reconnect_port in ports and not connected:
            self._schedule_reconnect()

    def _schedule_reconnect(self) -> None:
        """Cancel any pending reconnect timer and start a fresh 1-second debounce.

        The 1-second window absorbs USB re-enumeration bouncing (removed/attached
        cycling) so we only attempt the connection once the port has settled.
        """
        self._cancel_reconnect_timer()
        t = QTimer(self)
        t.setSingleShot(True)
        t.timeout.connect(self._attempt_reconnect)
        t.start(1000)
        self._reconnect_timer = t

    def _cancel_reconnect_timer(self) -> None:
        if self._reconnect_timer is not None:
            self._reconnect_timer.stop()
            self._reconnect_timer = None

    def _attempt_reconnect(self) -> None:
        self._reconnect_timer = None
        port = self._reconnect_port
        if not port or self.serial.is_connected():
            return
        if port not in self.serial.get_ports():
            if DEBUG:
                print(f"[DEBUG] Reconnect deferred — {port} not available yet")
            return
        try:
            baud = int(self._baud_combo.currentText())
            self.serial.connect(port, baudrate=baud)
            self._update_connect_button()
            self._reconnect_attempts = 0
            QTimer.singleShot(150, self._sync_repl)
            self.show_message(f"[PORT] Reconnected to {port}")
        except Exception as e:
            self._reconnect_attempts += 1
            if DEBUG:
                print(f"[DEBUG] Reconnect failed ({self._reconnect_attempts}): {e}")
            if self._reconnect_attempts < 5:
                self._schedule_reconnect()
            else:
                self._reconnect_attempts = 0
                self.show_message(f"[PORT] Auto-reconnect gave up after 5 attempts")

    # ------------------------------------------------------------------
    # Line / event processing (runs in main thread via SerialBridge signals)
    # ------------------------------------------------------------------

    def _on_line_received(self, line: str) -> None:
        # Strip trailing CR/LF FIRST — the firmware terminates event lines with a
        # trailing "\r\r" ("...\x1b[0m\r\r"). Splitting before stripping would make
        # rsplit("\r")[-1] return "" and miss the "[EVENT " tag entirely.
        normalized = _strip_ansi(line).rstrip("\r\n")
        # Honor the firmware's in-place line rewrite (CR + erase-line): only the
        # segment after the last \r is actually displayed. Classify on that so a
        # leftover echo fragment like "repl> g\r[EVENT ...]" is still recognized
        # as an event — otherwise it hides the "[EVENT " tag and the event both
        # leaks onto the terminal (even with events off) and is never dispatched
        # to the sensor apps. Matches SerialResponseParser's \r handling.
        if "\r" in normalized:
            normalized = normalized.rsplit("\r", 1)[-1]
        normalized = normalized.strip()
        is_bare_prompt = normalized == "repl>"
        if normalized.startswith("repl> "):
            normalized = normalized[6:].lstrip()

        # After _strip_ansi the ANSI prefix is gone; only the bare-bracket form remains.
        is_event = normalized.startswith("[EVENT ")

        if not is_event or self._show_events:
            if is_bare_prompt and not self._show_echo:
                # With local echo off, keep the bare prompt on its own line with
                # no trailing newline so the firmware's command echo appends to it
                # ("repl> gpio 0 read") instead of dropping the command onto a
                # separate line below the prompt. Skip if we're already sitting at
                # a bare prompt — the firmware emits two in a row at startup, which
                # would otherwise concatenate into "repl> repl> ".
                if self._terminal.document().lastBlock().text().rstrip() != "repl>":
                    self._terminal.write("repl> ")
            else:
                self._terminal.write(line + "\n")

        if is_event:
            self._process_event_line(normalized)

        for cb in self._line_received_callbacks:
            try:
                cb(line)
            except Exception as e:
                if DEBUG:
                    print(f"[DEBUG][ERROR] line callback: {e}")

        if self._logging_enabled:
            self._write_log(" R", line)

    def _on_log_message(self, msg: str) -> None:
        self.show_message(msg)

    def _process_event_line(self, line: str) -> None:
        try:
            line = _strip_ansi(line).strip()
            if line.startswith("repl> "):
                line = line[6:].lstrip()
            if not line.startswith("[EVENT "):
                return

            bracket_end = line.find("]")
            if bracket_end == -1:
                return
            event_id_raw = line[7:bracket_end].strip()
            event_id = event_id_raw[2:] if event_id_raw.lower().startswith("0x") else event_id_raw

            remaining = line[bracket_end + 1:].strip()
            timestamp = ""
            data = ""
            if remaining.startswith("["):
                ts_end = remaining.find("]")
                if ts_end != -1:
                    timestamp = remaining[1:ts_end].strip()
                    data = remaining[ts_end + 1:].strip()
            else:
                data = remaining

            for key in (event_id, event_id_raw):
                for cb in self._event_callbacks.get(key, []):
                    try:
                        cb(timestamp, data)
                    except Exception as e:
                        if DEBUG:
                            print(f"[DEBUG][ERROR] event callback {key}: {e}")
        except Exception as e:
            if DEBUG:
                print(f"[DEBUG][ERROR] _process_event_line: {e}")

    # ------------------------------------------------------------------
    # Public API (matches old SerialTerminal)
    # ------------------------------------------------------------------

    def register_event_callback(self, event_id: str, callback: Callable[[str, str], None]) -> None:
        if event_id not in self._event_callbacks:
            self._event_callbacks[event_id] = []
            self._enable_event(event_id)
        self._event_callbacks[event_id].append(callback)

    def register_connection_state_callback(self, callback: Callable[[], None]) -> None:
        self._connection_callbacks.append(callback)

    def register_line_received_callback(self, callback: Callable[[str], None]) -> None:
        self._line_received_callbacks.append(callback)

    def register_send_callback(self, callback: Callable[[str], None]) -> None:
        """Fires after every successful send_command() call with the sent text (stripped)."""
        self._send_callbacks.append(callback)

    @property
    def show_events(self) -> bool:
        return self._show_events

    def _enable_event(self, event_id: str) -> None:
        if self.serial.is_connected():
            self.send_command(f"event enable {event_id}\n")
        else:
            self._pending_event_enables.add(event_id)

    def _send_pending_events(self) -> None:
        for hex_id in self._pending_event_enables:
            self.send_command(f"event enable {hex_id}\n")
        self._pending_event_enables.clear()

    def send_command(self, command: str | None = None) -> bool:
        from_ui = command is None
        if from_ui:
            command = self._cmd_entry.text()
            if not command:
                return False

        if not self.serial.is_connected():
            if from_ui:
                self.show_message("\x1b[31mError: Serial port not connected\x1b[0m")
            return False

        if not command.endswith("\n"):
            command += "\n"

        if from_ui:
            stripped = command.rstrip("\n")
            if stripped and (not self._history or self._history[-1] != stripped):
                self._history.append(stripped)
            self._history_index = -1

        success = self.serial.send(command)
        if success:
            if self._logging_enabled:
                self._write_log("T ", command)
            if self._show_echo:
                self.show_message(f"\x1b[32m> {command.rstrip()}\x1b[0m")
        elif from_ui:
            self.show_message("\x1b[31mError: Failed to send command\x1b[0m")

        if from_ui and success:
            self._cmd_entry.selectAll()

        if success:
            cmd_text = command.strip()
            for cb in self._send_callbacks:
                try:
                    cb(cmd_text)
                except Exception:
                    pass

        return success

    def show_message(self, message: str) -> None:
        self._terminal.write(f"\x1b[95m{_strip_ansi(message)}\x1b[0m\n")

    def update_connection_state(self) -> None:
        self._update_connect_button()

    def close(self) -> None:
        self._save_config()
        if self._logging_enabled:
            self._stop_logging()
        self.serial.close()

    # ------------------------------------------------------------------
    # Command history
    # ------------------------------------------------------------------

    def _history_prev(self) -> None:
        if not self._history:
            return
        if self._history_index == -1:
            self._history_temp = self._cmd_entry.text()
            self._history_index = 0
        elif self._history_index < len(self._history) - 1:
            self._history_index += 1
        else:
            return
        self._cmd_entry.setText(self._history[-(self._history_index + 1)])
        self._cmd_entry.end(False)

    def _history_next(self) -> None:
        if self._history_index <= 0:
            if self._history_index == 0:
                self._history_index = -1
                self._cmd_entry.setText(self._history_temp)
            return
        self._history_index -= 1
        self._cmd_entry.setText(self._history[-(self._history_index + 1)])
        self._cmd_entry.end(False)

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    def _on_autoscroll_toggled(self, checked: bool) -> None:
        self._terminal.set_autoscroll(checked)

    def _send_from_ui(self) -> None:
        self.send_command()

    def _save_config(self) -> None:
        try:
            self._cfg.port = self._port_combo.currentText()
            self._cfg.baudrate = int(self._baud_combo.currentText())
            self._cfg.auto_scroll = self._autoscroll_cb.isChecked()
            self._cfg.logging_enabled = self._logging_checkbox.isChecked()
            self._cfg.show_events = self._show_events
            self._cfg.local_echo = self._show_echo
            self._cfg.terminal_max_width = self._terminal.max_lines
            pool.save()
        except Exception as e:
            if DEBUG:
                print(f"[DEBUG][ERROR] saving serial config: {e}")
