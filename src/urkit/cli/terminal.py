"""Cross-platform raw terminal input for the interactive CLIs.

The CLIs need three things from the platform:

1. Raw mode on stdin (no line buffering, no echo) with a way to
   restore the original settings, even on error paths.
2. Non-blocking input reads: "is there input?" and "read everything
   currently buffered" (a burst, e.g. the 3-byte arrow-key sequence).
3. On Windows only: ANSI escape processing on stdout so colors and
   cursor codes render.

Unix backend: termios + select, the same syscalls the CLIs used to
issue directly.

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
import threading
import time
from typing import Any, Callable

if sys.platform == "win32":
    import msvcrt
else:
    import select
    import termios

if sys.platform == "win32":
    # CDLL is used instead of WinDLL because ctypes.WinDLL is only
    # exposed in the Windows type stubs; on 64-bit Windows both use
    # the same calling convention.
    _kernel32 = ctypes.CDLL("kernel32", use_last_error=True)
    # Declare prototypes. The default restype is c_int, which would
    # truncate 64-bit HANDLE values from GetStdHandle.
    _kernel32.GetStdHandle.argtypes = [ctypes.c_int]
    _kernel32.GetStdHandle.restype = ctypes.c_void_p
    _kernel32.GetConsoleMode.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    _kernel32.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    _STD_INPUT_HANDLE = -10
    _STD_OUTPUT_HANDLE = -11
    _ENABLE_PROCESSED_INPUT = 0x0001
    _ENABLE_LINE_INPUT = 0x0002
    _ENABLE_ECHO_INPUT = 0x0004
    _ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004

    # msvcrt extended-key scan codes after the 0xE0 prefix byte, mapped
    # to the ANSI CSI sequences a Unix terminal emits for the same key.
    # Keys carrying the 0x00 prefix are not translated: their scan codes
    # overlap with arrow keys, and the CLIs don't use them.
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

    _WIN_ERROR_TEXT = {
        5: "access denied",
        6: "invalid handle",
        87: "invalid parameter",
        1225: "session disconnected",
    }

    def _win_error_detail() -> str:
        code = ctypes.get_last_error()
        return f"Win32 error {code} ({_WIN_ERROR_TEXT.get(code, 'unknown')})"

    def _console_mode(handle: int) -> int:
        mode = ctypes.c_uint32()
        if not _kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            raise OSError(
                f"GetConsoleMode failed ({_win_error_detail()}). stdin is "
                "not a usable console handle; run urkit from an "
                "interactive shell such as cmd or PowerShell."
            )
        return mode.value

    def _set_console_mode(handle: int, mode: int, context: str) -> None:
        if not _kernel32.SetConsoleMode(handle, mode):
            raise OSError(
                f"SetConsoleMode failed while {context} "
                f"({_win_error_detail()}, requested mode "
                f"0x{mode:08x}). The Windows console refused the "
                "terminal mode change."
            )

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
                handle,
                mode | _ENABLE_VIRTUAL_TERMINAL_PROCESSING,
                "enabling ANSI output",
            )
        except OSError:
            pass


input_active = threading.Event()
"""Set while CLI code is actively reading stdin (input-wait loops, text
prompts, menus). The Windows interrupt watcher stays out of the console
input queue while this is set, so it can never steal a keystroke from
the main reader. Callers set it around their read sections and clear it
afterwards."""


watcher_stop = threading.Event()
"""Set when the CLI begins its own shutdown (normal exit, fault exit,
Ctrl+C in the main loop). The Windows interrupt watcher exits quietly
without firing, so it cannot race the main thread's cleanup (double
robot stop, double terminal restore)."""


def stop_interrupt_watcher() -> None:
    """Tell the interrupt watcher to exit quietly. No-op on non-Windows."""
    watcher_stop.set()


def start_interrupt_watcher(
    on_fire: Callable[[str], None],
    fault_reason: Callable[[], str | None],
) -> threading.Thread | None:
    """Start the Windows-only interrupt watcher. Returns None elsewhere.

    On Windows, while the main thread is blocked in a long RTDE call
    (not reading input) nothing can interrupt it: Ctrl+C is a raw
    console byte that only the input loops read, and there is no
    SIGALRM. This daemon thread covers that gap. It polls, only while
    input_active is clear:

    - fault_reason() for a connection/robot fault
    - the console for a Ctrl+C (0x03) byte; any other byte is pushed
      back with ungetch() so the main reader still sees it, and the
      watcher backs off to avoid interfering with resumed input

    When either fires it calls on_fire(reason) exactly once; the
    caller should clean up (stop robot, restore terminal) and exit.
    """
    if sys.platform != "win32":
        return None

    # Only reachable on Windows (guard above), so this never runs on
    # Linux. Local import because mypy prunes the top-level platform
    # guard and cannot see the module inside this closure.
    import msvcrt

    def _where_blocked() -> None:
        # Diagnostic: report where the main thread was stuck so the
        # next occurrence can be diagnosed (usually a blocking socket
        # read inside ur_rtde with no timeout).
        frame = sys._current_frames().get(threading.main_thread().ident)
        if frame is None:
            return
        code = frame.f_code
        sys.stderr.write(
            "[urkit] main thread blocked in "
            f"{os.path.basename(code.co_filename)}:{frame.f_lineno} "
            f"in {code.co_name}\n"
        )
        sys.stderr.flush()

    def _run() -> None:
        backoff = 0.0
        while not watcher_stop.is_set():
            if backoff > 0:
                time.sleep(backoff)
                backoff = 0.0
            if input_active.is_set():
                time.sleep(0.05)
                continue
            reason = fault_reason()
            if reason is not None:
                _where_blocked()
                on_fire(reason)
                return
            try:
                if not msvcrt.kbhit():
                    time.sleep(0.05)
                    continue
                byte = msvcrt.getch()
            except OSError:
                # Console is closing (shutdown in progress). The watcher
                # is best-effort; exit quietly instead of dying with a
                # traceback that races the main thread's exit.
                return
            if byte == b"\x03":
                _where_blocked()
                on_fire("Interrupted.")
                return
            # Not Ctrl+C: give the byte back and back off so the main
            # reader (resuming from a blocking call) processes it.
            try:
                msvcrt.ungetch(byte[0])
            except OSError:
                return
            backoff = 0.2

    watcher = threading.Thread(
        target=_run, daemon=True, name="interrupt-watcher"
    )
    watcher.start()
    return watcher


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
            if not self._stdin_handle:
                raise OSError(
                    "stdin is not attached to a Windows console; run "
                    "urkit from an interactive shell such as cmd or "
                    "PowerShell."
                )
            self._old_mode = _console_mode(self._stdin_handle)
            # Disable processed input, line input, and echo. Ctrl+C
            # arrives as raw byte 0x03 (handled by the CLIs) instead
            # of KeyboardInterrupt, which would skip terminal restore.
            # Echo is always off: some consoles refuse raw mode with
            # echo still enabled, and the CLIs render input themselves.
            _set_console_mode(
                self._stdin_handle,
                self._old_mode
                & ~(
                    _ENABLE_PROCESSED_INPUT
                    | _ENABLE_LINE_INPUT
                    | _ENABLE_ECHO_INPUT
                ),
                "entering raw mode",
            )
            _enable_ansi_output()
        else:
            self._old_settings = termios.tcgetattr(sys.stdin)
            # No canonical mode, no echo; ISIG stays on so Ctrl+C
            # still raises KeyboardInterrupt. Same state as the
            # pre-shim menus and input prompts.
            settings = termios.tcgetattr(sys.stdin)
            settings[3] = settings[3] & ~(termios.ICANON | termios.ECHO)
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)
        self._enabled = True

    def disable(self) -> None:
        """Restore the original terminal settings. Idempotent."""
        if not self._enabled:
            return
        if sys.platform == "win32":
            if self._stdin_handle is None or self._old_mode is None:
                raise RuntimeError("RawTerminal disabled before enable()")
            _set_console_mode(
                self._stdin_handle, self._old_mode, "restoring terminal"
            )
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
            if byte == b"\xe0":
                # getch() returns bytes; the scan code dict is keyed
                # by int, so take the single byte's ordinal
                code = msvcrt.getch()[0]
                seq = _EXTENDED_KEYS.get(code)
                if seq is None:
                    # Unrecognized extended key: drop it
                    continue
                out += seq.encode("ascii")
            elif byte == b"\x00":
                # Untranslated extended prefix: consume the scan code
                msvcrt.getch()
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
