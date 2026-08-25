"""Tests for _message_line: severity-based status message coloring.

Failures must render red so they stand out on the pendant screen;
cancellations and missing-capability notices yellow; completed actions
green; everything else plain.
"""

from __future__ import annotations

import pytest

from urkit.cli.colors import red, green, yellow
from urkit.cli.teach import _message_line

WIDTH = 72


class TestRedFailures:
    @pytest.mark.parametrize(
        "msg",
        [
            "Error: Linear move failed: [WinError 1] Incorrect function",
            "Unreachable: step would exceed joint limits",
            "Unreachable: 'home' — no IK solution",
            "Unreachable: TCP +X — no IK solution",
            "Invalid step value",
            "Invalid speed value",
            "Gripper error: connection closed",
            "Freedrive error: not allowed in this mode",
            "stopScript failed: [WinError 1] Incorrect function",
        ],
    )
    def test_failures_are_red(self, msg: str):
        assert _message_line(msg, WIDTH) == f"  {red(msg[: WIDTH - 4])}"


class TestGreenSuccess:
    @pytest.mark.parametrize(
        "msg",
        [
            "Saved 'home'",
            "Moved to 'home' (cartesian)",
            "Deleted 'old_point'",
            "Renamed 'a' → 'b'",
        ],
    )
    def test_success_is_green(self, msg: str):
        assert _message_line(msg, WIDTH) == f"  {green(msg[: WIDTH - 4])}"


class TestYellowWarnings:
    @pytest.mark.parametrize(
        "msg",
        [
            "Cancelled",
            "Cancelled — at least 1 axis must be active",
            "Move to 'home' cancelled",
            "No saved points",
            "No gripper configured",
            "No points database configured",
            "Force not available for this gripper",
            "Speed not available for this gripper",
            "TCP Orient unavailable in TOOL frame",
        ],
    )
    def test_warnings_are_yellow(self, msg: str):
        assert _message_line(msg, WIDTH) == f"  {yellow(msg[: WIDTH - 4])}"


class TestPlainInfo:
    @pytest.mark.parametrize(
        "msg",
        [
            "Go To mode: Cartesian",
            "Move frame: TOOL",
            "Speed slider: 50%",
            "Step sizes reset to defaults",
            "Gripper set to 50%",
            "Config saved to config.yaml",
            "TCP oriented +X",
            "Freedrive axes: X+Y+Z",
        ],
    )
    def test_info_is_plain(self, msg: str):
        assert _message_line(msg, WIDTH) == f"  {msg[: WIDTH - 4]}"

    def test_long_message_truncated(self):
        import re

        msg = "Error: " + "x" * 200
        line = _message_line(msg, WIDTH)
        visible = re.sub(r"\033\[[0-9;]*m", "", line)
        assert len(visible) == 2 + WIDTH - 4
