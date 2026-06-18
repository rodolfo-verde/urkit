"""Tests for gripper activation behavior."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from urkit.exceptions import GripperError
from urkit.gripper.digital import DigitalGripper
from urkit.gripper.robotiq import RobotiqGripper


@pytest.fixture
def mock_rtde():
    mock = MagicMock()
    mock.sendCustomScriptFunction.return_value = True
    return mock


@pytest.fixture
def mock_rtde_r():
    return MagicMock()


# ------------------------------------------------------------------
# RobotiqGripper activation tests
# ------------------------------------------------------------------


class TestRobotiqActivation:

    @pytest.fixture(autouse=True)
    def _gripper(self, mock_rtde):
        self.rtde = mock_rtde
        self.gripper = RobotiqGripper(rtde_control=mock_rtde)

    def test_is_activated_initially_false(self):
        """Gripper starts unactivated."""
        assert self.gripper.is_activated() is False

    def test_open_without_activate_raises(self):
        """open() raises if gripper is not activated."""
        with pytest.raises(GripperError, match="not activated"):
            self.gripper.open()

    def test_close_without_activate_raises(self):
        """close() raises if gripper is not activated."""
        with pytest.raises(GripperError, match="not activated"):
            self.gripper.close()

    def test_set_position_without_activate_raises(self):
        """set_position() raises if gripper is not activated."""
        with pytest.raises(GripperError, match="not activated"):
            self.gripper.set_position(50)

    def test_activate_sends_script_and_sets_flag(self):
        """activate() sends the preamble+activation script and sets _activated."""
        self.gripper.activate()
        assert self.gripper.is_activated() is True
        self.rtde.sendCustomScriptFunction.assert_called()
        # First call is the activation script (preamble + rq_activate_and_wait())
        call = self.rtde.sendCustomScriptFunction.call_args_list[0]
        assert call[0][0] == "_gripper_cmd"
        code = call[0][1]
        assert "rq_activate_and_wait()" in code

    def test_activate_is_idempotent(self):
        """Second activate() call is a no-op (local flag)."""
        self.gripper.activate()
        self.gripper.activate()
        # 1 script sent (check+activate+open combined), second call is no-op
        assert self.rtde.sendCustomScriptFunction.call_count == 1

    def test_open_after_activate(self):
        """open() works after activate()."""
        self.gripper.activate()
        self.gripper.open()
        # activate (combined check+activate+open) + open = 2 calls
        assert self.rtde.sendCustomScriptFunction.call_count == 2

    def test_close_after_activate(self):
        """close() works after activate()."""
        self.gripper.activate()
        self.gripper.close()
        # activate (combined check+activate+open) + close = 2 calls
        assert self.rtde.sendCustomScriptFunction.call_count == 2

    def test_set_position_after_activate(self):
        """set_position() works after activate()."""
        self.gripper.activate()
        self.gripper.set_position(25)
        # activate (combined check+activate+open) + set_position = 2 calls
        assert self.rtde.sendCustomScriptFunction.call_count == 2

    def test_requires_rtde_control(self):
        """RobotiqGripper raises if rtde_control is None."""
        with pytest.raises(GripperError, match="rtde_control"):
            RobotiqGripper(rtde_control=None)

    def test_disconnect_resets_activation(self):
        """disconnect() resets activation flag; next activate re-checks state."""
        self.gripper.activate()
        assert self.gripper.is_activated() is True
        first_count = self.rtde.sendCustomScriptFunction.call_count
        self.gripper.disconnect()
        assert self.gripper.is_activated() is False
        # After disconnect, activate sends a new script
        self.gripper.activate()
        assert self.rtde.sendCustomScriptFunction.call_count == first_count + 1

    def test_after_disconnect_must_reactivate(self):
        """After disconnect, operations raise until activate() is called."""
        self.gripper.activate()
        self.gripper.disconnect()
        with pytest.raises(GripperError, match="not activated"):
            self.gripper.open()

    def test_get_position_mm_initially_none(self):
        """get_position_mm() returns None before any operation."""
        assert self.gripper.get_position_mm() is None

    def test_get_position_mm_after_activate(self):
        """get_position_mm() returns max_mm after activation (gripper opens)."""
        self.gripper.activate()
        assert self.gripper.get_position_mm() == 50.0  # default max_mm

    def test_get_position_mm_after_open(self):
        """get_position_mm() returns max_mm after open()."""
        self.gripper.activate()
        self.gripper.open()
        assert self.gripper.get_position_mm() == 50.0

    def test_get_position_mm_after_close(self):
        """get_position_mm() returns 0 after close()."""
        self.gripper.activate()
        self.gripper.close()
        assert self.gripper.get_position_mm() == 0.0

    def test_get_position_mm_after_set_position(self):
        """get_position_mm() returns the commanded position."""
        self.gripper.activate()
        self.gripper.set_position(25)
        assert self.gripper.get_position_mm() == 25.0

    def test_get_position_mm_after_disconnect(self):
        """get_position_mm() returns None after disconnect."""
        self.gripper.activate()
        self.gripper.set_position(30)
        self.gripper.disconnect()
        assert self.gripper.get_position_mm() is None

    def test_max_travel_mm(self):
        """max_travel_mm() returns the configured max_mm."""
        assert self.gripper.max_travel_mm() == 50.0

    def test_max_travel_mm_custom(self):
        """max_travel_mm() returns the custom max_mm value."""
        gripper = RobotiqGripper(rtde_control=self.rtde, max_mm=140)
        assert gripper.max_travel_mm() == 140.0

    def test_read_hardware_no_rtde_receive(self):
        """_read_position_from_hardware returns None without rtde_receive."""
        assert self.gripper._read_position_from_hardware() is None

    def test_read_hardware_not_activated(self, mock_rtde_r):
        """_read_position_from_hardware returns None when not activated."""
        self.gripper._rtde_r = mock_rtde_r
        assert self.gripper._read_position_from_hardware() is None

    def test_read_hardware_roundtrip(self, mock_rtde_r):
        """Hardware read encodes/decodes position via DO bits correctly."""
        self.gripper.activate()
        self.gripper._rtde_r = mock_rtde_r
        # Simulate raw=128 (half closed) → DO bits for 10000000 → bit 7 set
        # DO 8-15: bit 7 of raw maps to DO 15 (8+7)
        raw = 128
        do_bits = 0
        for i in range(8):
            if raw & (1 << i):
                do_bits |= 1 << (8 + i)
        mock_rtde_r.getActualDigitalOutputBits.return_value = do_bits
        mm = self.gripper._read_position_from_hardware()
        # raw=128 → mm = 50 * (1 - 128/255) = 24.9
        assert mm is not None
        assert abs(mm - 24.9) < 0.1

    def test_read_hardware_fully_open(self, mock_rtde_r):
        """raw=0 means fully open → max_mm."""
        self.gripper.activate()
        self.gripper._rtde_r = mock_rtde_r
        mock_rtde_r.getActualDigitalOutputBits.return_value = 0
        mm = self.gripper._read_position_from_hardware()
        assert mm == 50.0

    def test_read_hardware_fully_closed(self, mock_rtde_r):
        """raw=255 means fully closed → 0mm."""
        self.gripper.activate()
        self.gripper._rtde_r = mock_rtde_r
        # raw=255 → all DO 8-15 set → 0xFF00
        mock_rtde_r.getActualDigitalOutputBits.return_value = 0xFF00
        mm = self.gripper._read_position_from_hardware()
        assert mm == 0.0

    def test_get_position_mm_fallback(self):
        """get_position_mm falls back to tracked position when hw unavailable."""
        self.gripper.activate()
        self.gripper.set_position(30)
        # No rtde_receive → hardware read returns None → falls back to tracked
        assert self.gripper.get_position_mm() == 30.0


# ------------------------------------------------------------------
# DigitalGripper activation tests
# ------------------------------------------------------------------

class TestDigitalActivation:

    def test_activate_raises(self, mock_rtde, mock_rtde_r):
        gripper = DigitalGripper(mock_rtde, mock_rtde_r, pin=0)
        with pytest.raises(GripperError, match="do not require activation"):
            gripper.activate()

    def test_open_without_activate(self, mock_rtde, mock_rtde_r):
        """Digital gripper doesn't require activation."""
        gripper = DigitalGripper(mock_rtde, mock_rtde_r, pin=0)
        gripper.open()
        mock_rtde.setStandardDigitalOut.assert_called_with(0, False)

    def test_close_without_activate(self, mock_rtde, mock_rtde_r):
        gripper = DigitalGripper(mock_rtde, mock_rtde_r, pin=0)
        gripper.close()
        mock_rtde.setStandardDigitalOut.assert_called_with(0, True)

    def test_closed_when_high_false(self, mock_rtde, mock_rtde_r):
        gripper = DigitalGripper(mock_rtde, mock_rtde_r, pin=1, closed_when_high=False)
        gripper.open()
        mock_rtde.setStandardDigitalOut.assert_called_with(1, True)
        gripper.close()
        mock_rtde.setStandardDigitalOut.assert_called_with(1, False)

    def test_is_connected_raises(self, mock_rtde, mock_rtde_r):
        gripper = DigitalGripper(mock_rtde, mock_rtde_r, pin=0)
        with pytest.raises(GripperError, match="do not support connection"):
            gripper.is_connected()

    def test_set_position_raises(self, mock_rtde, mock_rtde_r):
        gripper = DigitalGripper(mock_rtde, mock_rtde_r, pin=0)
        with pytest.raises(GripperError, match="do not support set_position"):
            gripper.set_position(0)

    def test_set_force_raises(self, mock_rtde, mock_rtde_r):
        gripper = DigitalGripper(mock_rtde, mock_rtde_r, pin=0)
        with pytest.raises(GripperError, match="do not support set_force"):
            gripper.set_force(50)

    def test_set_speed_raises(self, mock_rtde, mock_rtde_r):
        gripper = DigitalGripper(mock_rtde, mock_rtde_r, pin=0)
        with pytest.raises(GripperError, match="do not support set_speed"):
            gripper.set_speed(50)
