"""Cross-platform raw terminal input for the interactive CLIs.

The CLIs need three things from the platform:

1. Raw mode on stdin (no line buffering, no echo) with a way to
   restore the original settings, even on error paths.
2. Non-blocking input reads: "is there input?" and "read everything
   currently buffered" (a burst, e.g. the 3-byte arrow-key sequence).
3. On Windows only: ANSI escape processing on stdout so colors and
   cursor codes render.

Unix backend: termios + tty + select, exactly the syscalls the CLIs
used to issue directly.

Windows backend: msvcrt with console input mode changed via kernel32.
The console does not emit ANSI sequences for special keys, so the
backend translates extended keycodes (prefix byte 0xE0/0x00 + scan
code) into the same byte sequences a Unix terminal sends. This keeps
the CLI key-parsing code identical on both platforms.

Windows limitation: with ENABLE_PROCESSED_INPUT disabled, Ctrl+C is
delivered as a raw 0x03 byte instead of raising KeyboardInterrupt.
The CLIs already handle 0x03 as an exit key, and it matters that
Ctrl+C is a byte rather than an exception here: an exception would
bypass terminal restore.
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from typing import Any

if sys.platform == "win32":
    import msvcrt
else:
    import select
    import termios
    import tty

if sys.platform == "win32":
    # CDLL is used instead of WinDLL because ctypes.WinDLL is only
    # exposed in the Windows type stubs; on 64-bit Windows both use
    # the same calling convention.
    _kernel32 = ctypes.CDLL("kernel32", use_last_error=True)
    _STD_INPUT_HANDLE = -10
    _STD_OUTPUT_HANDLE = -11
    _ENABLE_PROCESSED_INPUT = 0x0001
    _ENABLE_LINE_INPUT = 0x0002
    _ENABLE_ECHO_INPUT = 0x0004
    _ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

    # msvcrt extended-key scan codes (after the 0xE0/0x00 prefix byte)
    # mapped to the ANSI CSI sequences a Unix terminal emits for the
    # same key.
    _EXTENDED_KEYS: dict[int, str] = {
        0x48: "\x1b[A",  # Up
        0x50: "\x1b[B",  # Down
        0x4D: "\x1b[C",  # Right
        0x4B: "\x1b[D",  # Left
        0x47: "\x1b[H",  # Home
        0x4F: "\x1b[F",  # End
        0x49: "\x1b[5~",  # Page Up
        0x51: "\x1b[6~",  # Page Down
        0x52: "\x1b[2~",  # Insert
        0x53: "\x1b[3~",  # Delete
    }

    def _console_mode(handle: int) -> int:
        mode = ctypes.c_uint32()
        if not _kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            raise OSError(
                "GetConsoleMode failed (stdin is not a console). "
                "Run from an interactive shell."
            )
        return mode.value

    def _set_console_mode(handle: int, mode: int) -> None:
        if not _kernel32.SetConsoleMode(handle, mode):
            raise OSError("SetConsoleMode failed")

    def _enable_ansi_output() -> None:
        """Enable ANSI escape processing on stdout.

        No-op on Windows Terminal and recent conhost; needed on
        older conhost versions. Best effort: some non-console
        stdout handles (redirected output) reject it.
        """
        try:
            handle = _kernel32.GetStdHandle(_STD_OUTPUT_HANDLE)
            mode = _console_mode(handle)
            _set_console_mode(
                handle, mode | _ENABLE_VIRTUAL_TERMINAL_PROCESSING
            )
        except OSError:
            pass


def warn_if_windows() -> None:
    """Print a notice when the interactive CLI runs on Windows.

    Call at the top of interactive CLI commands. No-op on other
    platforms. Windows CLI support is not fully tested.
    """
    if sys.platform == "win32":
        print(
            "Warning: Windows CLI support is not fully tested and not "
            "officially supported. If you hit input or console problems, "
            "use Linux, macOS, or WSL2."
        )


class RawTerminal:
    """Raw (cbreak, no-echo) mode for stdin.

    Usage:
        with RawTerminal():
            ...
    or manually, where restore must also happen on explicit error
    paths:
        raw = RawTerminal()
        raw.enable()
        ...
        raw.disable()   # idempotent, safe to call multiple times
    """

    def __init__(self) -> None:
        self._enabled = False
        self._old_settings: list[Any] | None = None
        self._old_mode: int | None = None
        self._stdin_handle: int | None = None

    def enable(self) -> None:
        """Enter raw mode. Idempotent."""
        if self._enabled:
            return
        if sys.platform == "win32":
            self._stdin_handle = _kernel32.GetStdHandle(_STD_INPUT_HANDLE)
            self._old_mode = _console_mode(self._stdin_handle)
            # Disable processed input, line input, and echo. Ctrl+C
            # arrives as raw byte 0x03 (handled by the CLIs) instead
            # of KeyboardInterrupt, which would skip terminal restore.
            _set_console_mode(
                self._stdin_handle,
                self._old_mode
                & ~(
                    _ENABLE_PROCESSED_INPUT
                    | _ENABLE_LINE_INPUT
                    | _ENABLE_ECHO_INPUT
                ),
            )
            _enable_ansi_output()
        else:
            self._old_settings = termios.tcgetattr(sys.stdin)
            tty.setcbreak(sys.stdin.fileno())
        self._enabled = True

    def disable(self) -> None:
        """Restore the original terminal settings. Idempotent."""
        if not self._enabled:
            return
        if sys.platform == "win32":
            if self._stdin_handle is None or self._old_mode is None:
                raise RuntimeError("RawTerminal disabled before enable()")
            _set_console_mode(self._stdin_handle, self._old_mode)
        else:
            if self._old_settings is None:
                raise RuntimeError("RawTerminal disabled before enable()")
            termios.tcsetattr(
                sys.stdin, termios.TCSADRAIN, self._old_settings
            )
        self._enabled = False

    def __enter__(self) -> "RawTerminal":
        self.enable()
        return self

    def __exit__(self, *exc: object) -> None:
        self.disable()


def _win_read_pending() -> bytes:
    """Read all pending console input, translating extended keys to
    the ANSI CSI sequences a Unix terminal would have emitted."""
    if sys.platform == "win32":
        out = bytearray()
        while msvcrt.kbhit():
            byte = msvcrt.getch()
            if byte in (b"\xe0", b"\x00"):
                code = msvcrt.getch()
                seq = _EXTENDED_KEYS.get(code)
                if seq is None:
                    # Unrecognized function key (F1-F12 etc.): drop it
                    continue
                out += seq.encode("ascii")
            else:
                out += byte
        return bytes(out)
    raise RuntimeError("_win_read_pending is Windows-only")


def wait_input(timeout: float) -> bool:
    """Return True if any stdin input is available within timeout."""
    if sys.platform == "win32":
        deadline = time.monotonic() + timeout
        while not msvcrt.kbhit():
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.005)
        return True
    ready, _, _ = select.select([sys.stdin], [], [], timeout)
    return bool(ready)


def read_burst(timeout: float) -> bytes:
    """Wait up to timeout for input, then return everything currently
    buffered as one burst (e.g. the full \\x1b[A arrow-key sequence).

    Returns b"" if no input arrives within timeout.

    On Unix this is select() + a single os.read(), the same burst
    semantics as reading once after a select() notification. On
    Windows every pending key event is consumed.
    """
    if sys.platform == "win32":
        if not wait_input(timeout):
            return b""
        return _win_read_pending()
    if not wait_input(timeout):
        return b""
    return os.read(sys.stdin.fileno(), 64)
