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


_watcher_thread: threading.Thread | None = None
"""The running interrupt watcher thread, so stop_interrupt_watcher()
can join it. A daemon thread that is still alive when the CLI starts
tearing down the console / interpreter prints the
'Exception in thread interrupt-watcher' cascade on exit."""


def stop_interrupt_watcher() -> None:
    """Tell the interrupt watcher to exit quietly and wait for it.

    No-op on non-Windows. Joins with a short timeout so the CLI never
    starts terminal restore or interpreter shutdown while the watcher
    is still calling into msvcrt. If the join times out (watcher stuck
    in a console call) the CLI proceeds anyway; the watcher's hardened
    loop still cannot raise in that case.
    """
    global _watcher_thread
    watcher_stop.set()
    thread = _watcher_thread
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout=1.0)
    if thread is _watcher_thread:
        _watcher_thread = None


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
    global _watcher_thread

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
        # Snapshot the module globals the loop touches. During
        # interpreter shutdown module dicts are torn down; reading a
        # global that is gone turns this dying thread into a traceback
        # that races the main thread's exit.
        stop = watcher_stop
        active = input_active
        try:
            backoff = 0.0
            while not stop.is_set():
                if backoff > 0:
                    time.sleep(backoff)
                    backoff = 0.0
                if active.is_set():
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
                    # Console is closing (shutdown in progress). The
                    # watcher is best-effort; exit quietly instead of
                    # dying with a traceback that races the main
                    # thread's exit.
                    return
                if byte == b"\x03":
                    _where_blocked()
                    on_fire("Interrupted.")
                    return
                # Not Ctrl+C: give the byte back and back off so the
                # main reader (resuming from a blocking call) processes
                # it.
                try:
                    msvcrt.ungetch(byte[0])
                except OSError:
                    return
                backoff = 0.2
        except BaseException:
            # The watcher is best-effort. Never let it raise, even
            # during shutdown: an uncaught thread exception here is
            # what produces the 'Exception in thread interrupt-watcher'
            # / 'Exception in threading.excepthook' cascade on exit.
            return

    watcher = threading.Thread(
        target=_run, daemon=True, name="interrupt-watcher"
    )
    watcher.start()
    _watcher_thread = watcher
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


# Final bytes that terminate a CSI sequence (0x40-0x7E).
_CSI_FINAL = frozenset(chr(c) for c in range(0x40, 0x7F))
_ESC_GRACE_S = 0.03
"""Grace period to decide between a bare ESC press and the first byte
of an escape sequence whose tail has not arrived yet. The Windows
console delivers whole sequences in one burst, so this path mostly
matters on Unix terminals under load."""
_escape_tail = ""
"""Leftover bytes of a split escape sequence from the previous burst.
A terminal can split a CSI sequence across two reads; without the
carry, the tail (e.g. '[A') would be parsed as ordinary characters."""


def _consume_escape(text: str, pos: int) -> tuple[int, bool]:
    """Parse the escape sequence starting at text[pos] ('\\x1b').

    Returns (end, bare): end is the index just past the complete
    sequence, or -1 when the burst ends mid-sequence. end == 1 with
    bare True is a single ESC byte, which at the tail of a burst is
    ambiguous (real ESC press vs first byte of a split sequence) and
    resolved by the caller with a grace wait.
    """
    n = len(text)
    if pos + 1 >= n:
        return pos + 1, True  # ESC at the tail of the burst
    if text[pos + 1] == "O":
        if pos + 2 >= n:
            return -1, False  # SS3 fragment
        return pos + 3, False
    if text[pos + 1] == "[":
        j = pos + 2
        while j < n and text[j] not in _CSI_FINAL:
            j += 1
        if j >= n:
            return -1, False  # CSI fragment
        return j + 1, False
    # ESC not starting a known sequence: bare ESC; the byte that
    # follows is parsed as its own character.
    return pos + 1, True


def read_chars(timeout: float) -> list[str]:
    """Read input for up to timeout and return the logical characters.

    Complete ANSI escape sequences are dropped (arrow keys, Home/End,
    PageUp/Down, F keys, ...): both the Windows console and Unix
terminals report an arrow key as the 3-byte CSI sequence \\x1b[A, so
iterating raw bytes would treat its ESC byte as a cancel press and its
final byte as an ordinary key (an up-arrow would fire the 'a' move
handler, a down-arrow the 'b' save-point handler). A real ESC press is
kept, because the CLIs use it as the cancel/exit key, and it is
disambiguated from a split sequence with a short grace wait.
    """
    global _escape_tail
    text = _escape_tail + read_burst(timeout).decode("ascii", errors="replace")
    _escape_tail = ""
    if not text:
        return []
    out: list[str] = []
    i = 0
    while True:
        n = len(text)
        while i < n:
            if text[i] != "\x1b":
                out.append(text[i])
                i += 1
                continue
            end, bare = _consume_escape(text, i)
            if end == 1 and bare and i + 1 >= n:
                break  # ESC at the burst tail: ambiguous, grace wait
            if end >= 1:
                if end == 1:
                    out.append("\x1b")  # bare ESC, not at the tail
                # else: complete sequence, drop it
                i = end
                continue
            break  # fragment at the tail: grace wait below
        if i >= n:
            break
        fragment = text[i:]
        more = read_burst(_ESC_GRACE_S).decode("ascii", errors="replace")
        if more:
            combined = fragment + more
            end, _ = _consume_escape(combined, 0)
            if end < 0:
                _escape_tail = combined  # still a fragment: carry on
                break
            if end == 1:
                out.append("\x1b")  # not a sequence: real ESC press
            text = combined[end:]
            i = 0
            continue
        if fragment == "\x1b":
            # No continuation arrived: a real ESC press.
            out.append("\x1b")
            i += 1
            continue
        _escape_tail = fragment
        break
    return out


def read_key(timeout: float) -> str | None:
    """Read one key press, for single-key main loops.

    Returns the last logical character of the burst, so a held-key
    repeat queue resolves to the newest press, or None for no input.
    Escape sequences never produce a key: an arrow key is \\x1b[A on
    both Windows and Unix, and taking the burst's last byte would fire
    the 'a' (move) / 'b' (save point) handlers.
    """
    chars = read_chars(timeout)
    if not chars:
        return None
    return chars[-1]
