"""Tests for the Gripper factory method."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from urkit.exceptions import GripperError
from urkit.gripper import DigitalGripper, RobotiqGripper
from urkit.gripper.base import Gripper


class TestGripperFactory:
    """Gripper.create() should return correct types."""

    def test_create_robotiq(self):
        mock_rtde = MagicMock()
        mock_rtde.sendCustomScriptFunction.return_value = True
        g = Gripper.create("robotiq", rtde_control=mock_rtde)
        assert isinstance(g, RobotiqGripper)
        assert isinstance(g, Gripper)

    def test_create_digital(self):
        mock_rtde_c = MagicMock()
        mock_rtde_r = MagicMock()
        g = Gripper.create("digital", rtde_control=mock_rtde_c, rtde_receive=mock_rtde_r)
        assert isinstance(g, DigitalGripper)
        assert isinstance(g, Gripper)

    def test_create_unknown_raises(self):
        with pytest.raises(GripperError, match="Unknown gripper backend"):
            Gripper.create("unknown", rtde_control=MagicMock())

    def test_create_empty_name_raises(self):
        with pytest.raises(GripperError, match="Unknown gripper backend"):
            Gripper.create("", rtde_control=MagicMock())


class TestRobotiqGripper:
    """RobotiqGripper specific tests."""

    @pytest.fixture(autouse=True)
    def _gripper(self, monkeypatch):
        mock_rtde = MagicMock()
        mock_rtde.sendCustomScriptFunction.return_value = True
        self.gripper = RobotiqGripper(rtde_control=mock_rtde)
        self.rtde = mock_rtde

    def test_init_validates_rtde(self):
        """Gripper initializes without errors."""
        assert self.gripper is not None

    def test_force_out_of_range_raises(self):
        with pytest.raises(GripperError, match=r"0[–-]100"):
            RobotiqGripper(rtde_control=MagicMock(), force=500)

    def test_force_negative_raises(self):
        with pytest.raises(GripperError, match=r"0[–-]100"):
            RobotiqGripper(rtde_control=MagicMock(), force=-10)

    def test_speed_out_of_range_raises(self):
        with pytest.raises(GripperError, match=r"0[–-]100"):
            RobotiqGripper(rtde_control=MagicMock(), speed=500)

    def test_open_without_activate_raises(self):
        """open() raises if gripper is not activated."""
        with pytest.raises(GripperError, match="not activated"):
            self.gripper.open()

    def test_close_without_activate_raises(self):
        """close() raises if gripper is not activated."""
        with pytest.raises(GripperError, match="not activated"):
            self.gripper.close()

    def test_open_sends_script_after_activate(self):
        """Verify open() sends gripper URScript via sendCustomScriptFunction."""
        self.gripper.activate()
        self.gripper.open()
        calls = self.rtde.sendCustomScriptFunction.call_args_list
        # activate (combined check+activate+open) + open = 2 calls
        assert len(calls) == 2
        # Check the activate call contains activation logic
        activate_code = calls[0][0][1]
        assert "rq_is_gripper_activated()" in activate_code
        assert "rq_activate_and_wait()" in activate_code
        assert "rq_open_and_wait()" in activate_code
        # Check the open-after-activate call contains rq_open_and_wait
        open_code = calls[1][0][1]
        assert "rq_open_and_wait()" in open_code

    def test_close_sends_script_after_activate(self):
        """Verify close() sends gripper URScript via sendCustomScriptFunction."""
        self.gripper.activate()
        self.gripper.close()
        calls = self.rtde.sendCustomScriptFunction.call_args_list
        # activate (combined check+activate+open) + close = 2 calls
        assert len(calls) == 2
        close_code = calls[1][0][1]
        assert "rq_close_and_wait()" in close_code

    def test_set_force(self):
        self.gripper.set_force(80)

    def test_set_force_out_of_range_raises(self):
        with pytest.raises(GripperError, match=r"0[–-]100"):
            self.gripper.set_force(200)

    def test_set_force_negative_raises(self):
        with pytest.raises(GripperError, match=r"0[–-]100"):
            self.gripper.set_force(-10)

    def test_set_speed(self):
        self.gripper.set_speed(50)

    def test_speed_out_of_range_raises(self):
        with pytest.raises(GripperError, match=r"0[–-]100"):
            self.gripper.set_speed(200)

    def test_speed_negative_raises(self):
        with pytest.raises(GripperError, match=r"0[–-]100"):
            self.gripper.set_speed(-10)

    def test_second_call_skips_activation(self):
        """Second command should be a single call (already activated)."""
        self.gripper.activate()
        self.gripper.open()  # activate (combined) + open = 2 calls
        first_count = self.rtde.sendCustomScriptFunction.call_count
        assert first_count == 2
        self.gripper.close()  # only rq_close_and_wait = 1 call (already activated)
        second_count = self.rtde.sendCustomScriptFunction.call_count
        assert second_count - first_count == 1

    def test_is_connected(self):
        assert self.gripper.is_connected() is True

    def test_disconnect_resets_activation(self):
        """disconnect() resets activation flag; must call activate() again."""
        self.gripper.activate()
        self.gripper.open()  # activate (combined) + open = 2 calls
        assert self.rtde.sendCustomScriptFunction.call_count == 2
        self.gripper.disconnect()
        self.gripper.activate()
        self.gripper.open()  # activate (combined) + open = 2 more calls
        assert self.rtde.sendCustomScriptFunction.call_count == 4


class TestDigitalGripper:
    """DigitalGripper specific tests."""

    def test_init_validates_pin(self):
        mock_rtde_c = MagicMock()
        mock_rtde_r = MagicMock()
        with pytest.raises(GripperError, match=r"0[–-]7"):
            DigitalGripper(mock_rtde_c, mock_rtde_r, pin=8)

    def test_init_negative_pin(self):
        mock_rtde_c = MagicMock()
        mock_rtde_r = MagicMock()
        with pytest.raises(GripperError, match=r"0[–-]7"):
            DigitalGripper(mock_rtde_c, mock_rtde_r, pin=-1)

    def test_open_calls_set_output_false(self):
        mock_rtde_c = MagicMock()
        mock_rtde_r = MagicMock()
        g = DigitalGripper(mock_rtde_c, mock_rtde_r, pin=3)
        g.open()
        mock_rtde_c.setStandardDigitalOut.assert_called_with(3, False)

    def test_close_calls_set_output_true(self):
        mock_rtde_c = MagicMock()
        mock_rtde_r = MagicMock()
        g = DigitalGripper(mock_rtde_c, mock_rtde_r, pin=3)
        g.close()
        mock_rtde_c.setStandardDigitalOut.assert_called_with(3, True)

    def test_closed_when_high_false_reverses(self):
        mock_rtde_c = MagicMock()
        mock_rtde_r = MagicMock()
        g = DigitalGripper(mock_rtde_c, mock_rtde_r, pin=2, closed_when_high=False)
        g.open()
        mock_rtde_c.setStandardDigitalOut.assert_called_with(2, True)
        g.close()
        mock_rtde_c.setStandardDigitalOut.assert_called_with(2, False)
