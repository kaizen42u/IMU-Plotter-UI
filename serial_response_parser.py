"""
Structured command → response tracker for the serial REPL protocol.

Firmware output per command
---------------------------
    <command echo>
    <response body lines …>
    OK | FAIL
    repl>

Usage
-----
    parser = SerialResponseParser(serial_terminal)

    # pre-register a callback before sending — the terminal send hook enqueues it
    parser.send("ledc show", lambda lines, status: handle(lines, status))

    # fire-and-forget with no callback — still tracked so the response is
    # consumed cleanly rather than landing in the debug buffer
    parser.send("ledc timer 1 config 5000")

    # background [EVENT] lines
    parser.register_event_callback(lambda line: log(line))

    # inspect lines that could not be attributed to any pending command
    print(parser.debug_buffer)

Notes
-----
* The parser hooks into register_send_callback so EVERY successful
  send_command() call is enqueued in the pending queue — including button
  clicks, slider dispatches, and user-typed commands.  Commands sent via
  parser.send() pre-stage their callback by command text so the hook can
  pick it up; all other sends have callback=None and are consumed silently.
* The parser processes lines on the main thread; no extra thread is created.
* [EVENT] lines (starting with "[EVENT ") are routed to event callbacks and
  never appear in a response body.
"""

import collections
import re
from typing import Callable


# Same pattern used by qt_serial_terminal._strip_ansi — covers both the full
# ESC-bracket form and the bare-bracket SGR form that survives after the
# terminal strips the \x1b prefix.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]|\[[0-9;]+[A-Za-z]")

def _strip_ansi(text: str) -> str:
    return _ANSI_RE.sub("", text)


_TERMINAL_TOKENS = frozenset({"OK", "FAIL"})


class SerialResponseParser:

    MAX_DEBUG = 500

    def __init__(self, serial_terminal) -> None:
        self._st = serial_terminal
        # (normalised_command, callback | None)
        self._pending: collections.deque[tuple[str, Callable | None]] = collections.deque()
        self._collecting = False
        self._body: list[str] = []

        # Pre-staged callbacks from parser.send(): cmd_text → deque[callback]
        # Keyed by command so interleaved sends with different commands stay ordered.
        self._staged: dict[str, collections.deque] = {}

        # Observable hooks
        self._event_cbs:    list[Callable[[str], None]] = []
        self._sent_cbs:     list[Callable[[str], None]] = []
        self._response_cbs: list[Callable[[str, list[str], str], None]] = []
        self._debug_cbs:    list[Callable[[str], None]] = []

        self._debug: collections.deque[str] = collections.deque(maxlen=self.MAX_DEBUG)

        serial_terminal.register_line_received_callback(self._on_line)
        serial_terminal.register_send_callback(self._on_any_send)

    # ------------------------------------------------------------------
    # Public API

    def send(
        self,
        cmd: str,
        callback: Callable[[list[str], str], None] | None = None,
    ) -> None:
        """
        Send *cmd* via the terminal and optionally receive the complete response.

        callback(lines: list[str], status: str) — called on the main thread
        once OK or FAIL is received.

        The terminal's register_send_callback hook will enqueue this command
        into pending; send() only pre-stages the callback so the hook can
        associate it.
        """
        normalised = cmd.strip()
        if callback is not None:
            self._staged.setdefault(normalised, collections.deque()).append(callback)
        if not cmd.endswith("\n"):
            cmd += "\n"
        self._st.send_command(cmd)

    # -- observer registration --

    def register_event_callback(self, callback: Callable[[str], None]) -> None:
        """Persistent callback for [EVENT] lines."""
        self._event_cbs.append(callback)

    def register_sent_callback(self, callback: Callable[[str], None]) -> None:
        """Called for every outgoing send_command(), with the normalised command text."""
        self._sent_cbs.append(callback)

    def register_response_callback(
        self, callback: Callable[[str, list[str], str], None]
    ) -> None:
        """Called when a response completes: callback(cmd, body_lines, status)."""
        self._response_cbs.append(callback)

    def register_debug_callback(self, callback: Callable[[str], None]) -> None:
        """Called for every line that lands in the debug buffer."""
        self._debug_cbs.append(callback)

    @property
    def debug_buffer(self) -> list[str]:
        """Lines that could not be attributed to any pending command."""
        return list(self._debug)

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def is_collecting(self) -> bool:
        return self._collecting

    @property
    def show_events(self) -> bool:
        return self._st.show_events

    # ------------------------------------------------------------------
    # Internal

    def _on_any_send(self, cmd: str) -> None:
        """Called for every successful send_command() — the single enqueue point."""
        normalised = cmd.strip()
        if not normalised:
            return
        # Claim a pre-staged callback if parser.send() registered one for this command.
        staged = self._staged.get(normalised)
        callback = staged.popleft() if staged else None
        if staged is not None and not staged:
            del self._staged[normalised]
        self._pending.append((normalised, callback))
        for cb in self._sent_cbs:
            try:
                cb(normalised)
            except Exception:
                pass

    def _on_line(self, raw: str) -> None:
        line = _strip_ansi(raw).rstrip("\r\n")
        stripped = line.strip()

        if not stripped:
            if self._collecting:
                self._body.append(line)
            return

        # Strip the repl> prompt prefix if present.
        # When the firmware processes a second command immediately, it echoes it
        # on the same line as the prompt: "repl> help ledc".  Discarding the
        # whole line would eat the echo and leave the pending entry stuck.
        if stripped == "repl>":
            return
        if stripped.startswith("repl> "):
            stripped = stripped[6:].strip()
            line = stripped
            if not stripped:
                return

        # Events — "[EVENT ...]" format used by the firmware; uppercase tag only.
        # After ANSI stripping, bare "[digits m]" remnants can't reach here anymore.
        if stripped.startswith("[EVENT "):
            for cb in self._event_cbs:
                try:
                    cb(stripped)
                except Exception:
                    pass
            return

        if not self._collecting:
            if self._pending and stripped == self._pending[0][0]:
                self._collecting = True
                self._body = []
            else:
                self._debug.append(line)
                for cb in self._debug_cbs:
                    try:
                        cb(line)
                    except Exception:
                        pass
        else:
            if stripped in _TERMINAL_TOKENS:
                cmd, callback = self._pending.popleft()
                body = [l for l in self._body if l.strip()]
                status = stripped
                if callback is not None:
                    try:
                        callback(body, status)
                    except Exception as e:
                        print(f"[ResponseParser] callback error for '{cmd}': {e}")
                for cb in self._response_cbs:
                    try:
                        cb(cmd, body, status)
                    except Exception:
                        pass
                self._collecting = False
                self._body = []
            else:
                self._body.append(line)
