"""Tests for the raw-input escape-sequence parsing in cli/terminal.

Arrow keys, Home/End and F keys arrive as ANSI CSI sequences
(\\x1b[A, \\x1b[H, ...) on both the Windows console (translated by
_win_read_pending) and Unix terminals. The parser must drop complete
sequences, keep a real ESC press, and survive a sequence split across
two reads. read_burst is patched so no real console I/O happens.
"""

from __future__ import annotations

import sys

import pytest

from urkit.cli import terminal


def _patch_bursts(monkeypatch: pytest.MonkeyPatch, bursts: list[bytes]) -> list[str]:
    """Feed a scripted sequence of bursts to read_burst (b"" = empty)."""
    calls: list[str] = []
    it = iter(bursts)

    def fake_burst(timeout: float) -> bytes:
        calls.append(f"{timeout:.3f}")
        try:
            return next(it)
        except StopIteration:
            return b""

    monkeypatch.setattr(terminal, "read_burst", fake_burst)
    return calls


def _reset_state() -> None:
    terminal._escape_tail = ""


class TestConsumeEscape:
    def test_complete_csi(self):
        assert terminal._consume_escape("\x1b[A", 0) == (3, False)

    def test_complete_csi_with_params(self):
        assert terminal._consume_escape("\x1b[5~", 0) == (4, False)

    def test_ss3_function_key(self):
        assert terminal._consume_escape("\x1bOP", 0) == (3, False)

    def test_bare_esc_at_tail(self):
        assert terminal._consume_escape("\x1b", 0) == (1, True)

    def test_bare_esc_followed_by_plain_byte(self):
        assert terminal._consume_escape("\x1ba", 0) == (1, True)

    def test_incomplete_csi(self):
        assert terminal._consume_escape("\x1b[", 0) == (-1, False)

    def test_incomplete_ss3(self):
        assert terminal._consume_escape("\x1bO", 0) == (-1, False)

    def test_sequence_not_at_start(self):
        assert terminal._consume_escape("x\x1b[B", 1) == (4, False)


class TestReadChars:
    def test_plain_chars(self, monkeypatch: pytest.MonkeyPatch):
        _reset_state()
        _patch_bursts(monkeypatch, [b"abc"])
        assert terminal.read_chars(0.0) == ["a", "b", "c"]

    def test_no_input(self, monkeypatch: pytest.MonkeyPatch):
        _reset_state()
        _patch_bursts(monkeypatch, [b""])
        assert terminal.read_chars(0.0) == []

    def test_arrow_up_dropped(self, monkeypatch: pytest.MonkeyPatch):
        _reset_state()
        _patch_bursts(monkeypatch, [b"\x1b[A"])
        assert terminal.read_chars(0.0) == []

    def test_arrow_down_dropped(self, monkeypatch: pytest.MonkeyPatch):
        _reset_state()
        _patch_bursts(monkeypatch, [b"\x1b[B"])
        assert terminal.read_chars(0.0) == []

    def test_home_end_dropped(self, monkeypatch: pytest.MonkeyPatch):
        _reset_state()
        _patch_bursts(monkeypatch, [b"\x1b[H", b"\x1b[F"])
        assert terminal.read_chars(0.0) == []
        assert terminal.read_chars(0.0) == []

    def test_page_up_params_dropped(self, monkeypatch: pytest.MonkeyPatch):
        _reset_state()
        _patch_bursts(monkeypatch, [b"\x1b[5~"])
        assert terminal.read_chars(0.0) == []

    def test_bare_esc_kept(self, monkeypatch: pytest.MonkeyPatch):
        # ESC alone, grace window comes back empty: real ESC press.
        _reset_state()
        _patch_bursts(monkeypatch, [b"\x1b", b""])
        assert terminal.read_chars(0.0) == ["\x1b"]

    def test_ctrl_c_kept(self, monkeypatch: pytest.MonkeyPatch):
        _reset_state()
        _patch_bursts(monkeypatch, [b"\x03"])
        assert terminal.read_chars(0.0) == ["\x03"]

    def test_char_before_arrow(self, monkeypatch: pytest.MonkeyPatch):
        _reset_state()
        _patch_bursts(monkeypatch, [b"a\x1b[A"])
        assert terminal.read_chars(0.0) == ["a"]

    def test_char_after_arrow(self, monkeypatch: pytest.MonkeyPatch):
        _reset_state()
        _patch_bursts(monkeypatch, [b"\x1b[Aa"])
        assert terminal.read_chars(0.0) == ["a"]

    def test_esc_followed_by_plain_key(self, monkeypatch: pytest.MonkeyPatch):
        # ESC then 'a' (in the grace window): both kept, in order.
        _reset_state()
        _patch_bursts(monkeypatch, [b"\x1b", b"a"])
        assert terminal.read_chars(0.0) == ["\x1b", "a"]

    def test_split_esc_then_tail(self, monkeypatch: pytest.MonkeyPatch):
        # ESC arrives alone, the CSI tail in the grace window.
        _reset_state()
        _patch_bursts(monkeypatch, [b"\x1b", b"[A"])
        assert terminal.read_chars(0.0) == []

    def test_split_csi_fragment_then_tail(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        # ESC [ arrives together, the final byte in the grace window.
        _reset_state()
        _patch_bursts(monkeypatch, [b"\x1b[", b"A"])
        assert terminal.read_chars(0.0) == []

    def test_fragment_carried_to_next_burst(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        # Fragment with an empty grace window: carried over, and the
        # next burst completes (then drops) the sequence.
        _reset_state()
        _patch_bursts(monkeypatch, [b"\x1b[", b"", b"A", b""])
        assert terminal.read_chars(0.0) == []
        assert terminal.read_chars(0.0) == []

    def test_stale_fragment_cost(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        # A fragment whose tail never arrives (a terminal that sent a
        # truncated CSI, a broken state) stays carried. When the next
        # input finally comes, the first byte completes (and is
        # dropped as) the sequence: one keystroke cost. Real terminals
        # always finish their sequences, so the common split cases
        # above are lossless.
        _reset_state()
        _patch_bursts(monkeypatch, [b"\x1b[", b"", b"zz", b""])
        assert terminal.read_chars(0.0) == []
        # "\x1b[" + "zz" -> CSI "\x1b[z" dropped, trailing 'z' kept
        assert terminal.read_chars(0.0) == ["z"]


@pytest.mark.skipif(
    sys.platform != "win32", reason="msvcrt console translation is Windows-only"
)
class TestWinReadPending:
    """_win_read_pending translates msvcrt key events (0xE0/0x00 prefix
    + scan code) into the ANSI CSI sequences a Unix terminal emits, so
    the shared parser sees identical input on both platforms."""

    def _feed(self, monkeypatch: pytest.MonkeyPatch, presses: list[bytes]) -> None:
        buf = bytearray(b"".join(presses))

        def kbhit() -> bool:
            return len(buf) > 0

        def getch() -> bytes:
            b = buf[0]
            del buf[0]
            return bytes([b])

        monkeypatch.setattr(terminal.msvcrt, "kbhit", kbhit)
        monkeypatch.setattr(terminal.msvcrt, "getch", getch)

    def test_no_input(self, monkeypatch: pytest.MonkeyPatch):
        self._feed(monkeypatch, [])
        assert terminal._win_read_pending() == b""

    def test_plain_byte_passthrough(self, monkeypatch: pytest.MonkeyPatch):
        self._feed(monkeypatch, [b"a", b"q"])
        assert terminal._win_read_pending() == b"aq"

    def test_all_mapped_extended_keys(self, monkeypatch: pytest.MonkeyPatch):
        # Every entry in the scan-code table must produce its CSI sequence.
        for scan, seq in terminal._EXTENDED_KEYS.items():
            self._feed(monkeypatch, [b"\xe0" + bytes([scan])])
            assert terminal._win_read_pending() == seq.encode("ascii"), seq

    def test_mixed_plain_and_extended(self, monkeypatch: pytest.MonkeyPatch):
        # 'a' then up-arrow (0xE0 0x48) then down-arrow (0xE0 0x50)
        self._feed(monkeypatch, [b"a", b"\xe0\x48", b"\xe0\x50"])
        assert terminal._win_read_pending() == b"a\x1b[A\x1b[B"

    def test_unmapped_extended_key_dropped(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        # F1 (scan 0x3B) is not in the table: consumed, not misread.
        self._feed(monkeypatch, [b"\xe0\x3b"])
        assert terminal._win_read_pending() == b""

    def test_zero_prefix_key_dropped(self, monkeypatch: pytest.MonkeyPatch):
        # 0x00-prefixed keys overlap arrow scan codes: prefix + scan
        # both consumed, nothing emitted.
        self._feed(monkeypatch, [b"\x00\x3b"])
        assert terminal._win_read_pending() == b""


class TestReadKey:
    def test_last_of_repeat_queue(self, monkeypatch: pytest.MonkeyPatch):
        _reset_state()
        _patch_bursts(monkeypatch, [b"aaaa"])
        assert terminal.read_key(0.0) == "a"

    def test_repeat_then_new_key(self, monkeypatch: pytest.MonkeyPatch):
        _reset_state()
        _patch_bursts(monkeypatch, [b"aaaq"])
        assert terminal.read_key(0.0) == "q"

    def test_arrow_is_not_a_key(self, monkeypatch: pytest.MonkeyPatch):
        # The original bug: taking the burst's last byte made
        # up-arrow fire 'a' (move) and down-arrow fire 'b' (save point).
        _reset_state()
        _patch_bursts(monkeypatch, [b"\x1b[A"])
        assert terminal.read_key(0.0) is None
        _patch_bursts(monkeypatch, [b"\x1b[B"])
        assert terminal.read_key(0.0) is None

    def test_bare_esc_is_a_key(self, monkeypatch: pytest.MonkeyPatch):
        _reset_state()
        _patch_bursts(monkeypatch, [b"\x1b", b""])
        assert terminal.read_key(0.0) == "\x1b"

    def test_no_input(self, monkeypatch: pytest.MonkeyPatch):
        _reset_state()
        _patch_bursts(monkeypatch, [b""])
        assert terminal.read_key(0.0) is None
