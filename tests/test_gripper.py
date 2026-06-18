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
        """get_position_mm() returns None after activation (gripper doesn't open)."""
        self.gripper.activate()
        assert self.gripper.get_position_mm() is None

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
