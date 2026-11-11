"""Tests for gripper activation behavior."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

import urkit.gripper.robotiq as robotiq_mod
from urkit.exceptions import GripperError
from urkit.gripper.digital import DigitalGripper
from urkit.gripper.robotiq import RobotiqGripper
from urkit.gripper.robotiq_preamble import ROBOTIQ_PREAMBLE


@pytest.fixture
def mock_rtde():
    mock = MagicMock()
    mock.sendCustomScriptFunction.return_value = True
    return mock


@pytest.fixture
def mock_rtde_r():
    mock = MagicMock()
    mock.getOutputIntRegister.return_value = 1
    return mock


# ------------------------------------------------------------------
# RobotiqGripper activation tests
# ------------------------------------------------------------------


class TestRobotiqActivation:

    @pytest.fixture(autouse=True)
    def _gripper(self, mock_rtde, mock_rtde_r):
        self.rtde = mock_rtde
        self.rtde_r = mock_rtde_r
        self.gripper = RobotiqGripper(
            rtde_control=mock_rtde, rtde_receive=mock_rtde_r
        )

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

    def test_set_position_mm_without_activate_raises(self):
        """set_position_mm() raises if gripper is not activated."""
        with pytest.raises(GripperError, match="not activated"):
            self.gripper.set_position_mm(50)

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

    def test_activate_script_is_bounded(self):
        """The activation script must terminate on its own (the
        process-poisoning fix)."""
        self.gripper.activate()
        code = self.rtde.sendCustomScriptFunction.call_args_list[0][0][1]
        # Activation gated on the preamble's bounded connection scan:
        # rq_activate() reaches rq_set_var()'s unbounded ack loop on a
        # socket with no gripper behind it.
        assert "if (gripper_1_connected):" in code
        assert "rq_activate_and_wait()" in code
        # Bounded activation wait (the official preamble loops forever).
        assert "act_retries < 50" in code

    def test_activate_no_gripper_times_out(self, monkeypatch):
        """With no gripper the preamble runs its full bounded scan, which
        exceeds the deadline: activate() must raise, not set the flag."""
        monkeypatch.setattr(robotiq_mod, "ACTIVATE_DEADLINE_S", 0.3)
        self.rtde.sendCustomScriptFunction.side_effect = lambda *a, **k: (
            time.sleep(2.0), True
        )[1]
        with pytest.raises(GripperError, match="did not complete"):
            self.gripper.activate()
        assert self.gripper.is_activated() is False
        assert self.gripper._activation_failed is True

    def test_activate_timeout_marks_activation_failed(self, monkeypatch):
        """A wedged sendCustomScriptFunction trips the watchdog and marks
        the activation as failed (so URRobot.disconnect() skips
        stopScript())."""
        monkeypatch.setattr(robotiq_mod, "ACTIVATE_DEADLINE_S", 0.3)
        self.rtde.sendCustomScriptFunction.side_effect = lambda *a, **k: (
            time.sleep(2.0), True
        )[1]
        with pytest.raises(GripperError, match="did not complete"):
            self.gripper.activate()
        assert self.gripper.is_activated() is False
        assert self.gripper._activation_failed is True

    def test_activate_in_progress_blocks_second_call(self):
        """A second activate() while the send thread is running raises
        instead of racing the RTDE control socket."""
        started = threading.Event()

        def slow_send(name, code):
            started.set()
            time.sleep(1.0)
            return True

        self.rtde.sendCustomScriptFunction.side_effect = slow_send
        t = threading.Thread(
            target=self.gripper.activate, kwargs={"timeout": 5.0}
        )
        t.start()
        assert started.wait(2.0)
        try:
            with pytest.raises(GripperError, match="already in progress"):
                self.gripper.activate()
        finally:
            t.join(5.0)
        assert self.gripper.is_activated() is True

    def test_activation_failed_reset_by_disconnect(self, monkeypatch):
        """disconnect() clears the failed flag so a later activate() is a
        fresh attempt."""
        monkeypatch.setattr(robotiq_mod, "ACTIVATE_DEADLINE_S", 0.3)
        self.rtde.sendCustomScriptFunction.side_effect = lambda *a, **k: (
            time.sleep(2.0), True
        )[1]
        with pytest.raises(GripperError):
            self.gripper.activate()
        assert self.gripper._activation_failed is True
        self.gripper.disconnect()
        assert self.gripper._activation_failed is False


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

    def test_set_position_mm_after_activate(self):
        """set_position_mm() works after activate()."""
        self.gripper.activate()
        self.gripper.set_position_mm(25)
        # activate (combined check+activate+open) + set_position_mm = 2 calls
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

    def test_get_position_mm_after_set_position_mm(self):
        """get_position_mm() returns the commanded position."""
        self.gripper.activate()
        self.gripper.set_position_mm(25)
        assert self.gripper.get_position_mm() == 25.0

    def test_get_position_mm_after_disconnect(self):
        """get_position_mm() returns None after disconnect."""
        self.gripper.activate()
        self.gripper.set_position_mm(30)
        self.gripper.disconnect()
        assert self.gripper.get_position_mm() is None

    def test_max_travel_mm(self):
        """max_travel_mm() returns the configured max_mm."""
        assert self.gripper.max_travel_mm() == 50.0

    def test_max_travel_mm_custom(self):
        """max_travel_mm() returns the custom max_mm value."""
        gripper = RobotiqGripper(
            rtde_control=self.rtde, rtde_receive=self.rtde_r, max_mm=140
        )
        assert gripper.max_travel_mm() == 140.0


class TestPreambleBoundedActivation:
    """The vendored preamble's rq_activate_and_wait() must be bounded.

    The official Robotiq preamble loops forever when no gripper is
    connected, which leaves the robot running the script (and the RTDE
    control register occupied) for the life of the process.
    """

    def test_activate_and_wait_has_retry_bound(self):
        assert "act_retries < 50" in ROBOTIQ_PREAMBLE
        assert "act_retries = act_retries + 1" in ROBOTIQ_PREAMBLE

    def test_no_unbounded_activation_loop(self):
        # The original unbounded loop has no exit condition.
        assert (
            "while(not rq_is_gripper_activated(gripper_socket)):"
            not in ROBOTIQ_PREAMBLE
        )


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

    def test_set_position_mm_raises(self, mock_rtde, mock_rtde_r):
        gripper = DigitalGripper(mock_rtde, mock_rtde_r, pin=0)
        with pytest.raises(GripperError, match="do not support set_position_mm"):
            gripper.set_position_mm(0)

    def test_set_force_raises(self, mock_rtde, mock_rtde_r):
        gripper = DigitalGripper(mock_rtde, mock_rtde_r, pin=0)
        with pytest.raises(GripperError, match="do not support set_force"):
            gripper.set_force(50)

    def test_set_speed_raises(self, mock_rtde, mock_rtde_r):
        gripper = DigitalGripper(mock_rtde, mock_rtde_r, pin=0)
        with pytest.raises(GripperError, match="do not support set_speed"):
            gripper.set_speed(50)
