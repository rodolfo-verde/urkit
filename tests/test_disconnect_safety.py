"""Tests for URRobot.disconnect() safety after a failed gripper activation.

A failed Robotiq activation leaves a bounded gripper script finishing on
the robot. stopScript() blocks in the ur_rtde C++ layer while that
script runs, so disconnect() must skip it on that path. These tests
cover the guard without a real robot.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from urkit.exceptions import GripperError
from urkit.gripper.robotiq import RobotiqGripper


def _make_robot(
    gripper: RobotiqGripper | None = None,
    gripper_activation_failed: bool = False,
) -> "object":
    """Build a URRobot with mocked subsystems (bypasses __init__)."""
    from urkit.robot import URRobot

    robot = object.__new__(URRobot)
    robot._ip = "127.0.0.1"
    robot._rtde_c = MagicMock()
    robot._rtde_r = MagicMock()
    robot._rtde_io = MagicMock()
    robot._connection_lost = False
    robot._gripper_activation_failed = gripper_activation_failed
    robot._motion = MagicMock()
    robot._gripper = gripper
    robot._dashboard = None
    robot._points = None
    return robot


def _failed_activation_gripper() -> RobotiqGripper:
    """A RobotiqGripper whose activate() failed (no gripper connected).

    The RTDE control channel is wedged: every send raises, so any
    activate() (at any timeout) fails and marks the activation failed.
    """
    rtde_c = MagicMock()
    rtde_r = MagicMock()
    rtde_c.sendCustomScriptFunction.side_effect = RuntimeError(
        "RTDE control channel wedged"
    )
    gripper = RobotiqGripper(rtde_control=rtde_c, rtde_receive=rtde_r)
    with pytest.raises(GripperError):
        gripper.activate()
    assert gripper._activation_failed is True
    return gripper


class TestDisconnectAfterFailedActivation:

    def test_disconnect_skips_stop_script(self):
        """disconnect() returns and does NOT call stopScript() after a
        failed activation (the C++ call blocks while the bounded gripper
        script is finishing)."""
        robot = _make_robot(gripper=_failed_activation_gripper())
        robot.disconnect()  # must not hang
        robot._motion.stop_script.assert_not_called()

    def test_disconnect_skips_stop_script_with_robot_flag(self):
        """The robot-side flag (set by _activate_gripper, which nulls out
        the gripper) is sufficient to skip stopScript()."""
        robot = _make_robot(
            gripper=None, gripper_activation_failed=True
        )
        robot.disconnect()
        robot._motion.stop_script.assert_not_called()

    def test_disconnect_stops_script_normally(self):
        """Without a gripper failure, stopScript() is called as before."""
        robot = _make_robot()
        robot.disconnect()
        robot._motion.stop_script.assert_called_once()

    def test_disconnect_stops_script_after_successful_activation(self):
        """A successfully activated gripper does not trigger the guard."""
        rtde_c = MagicMock()
        rtde_r = MagicMock()
        gripper = RobotiqGripper(rtde_control=rtde_c, rtde_receive=rtde_r)
        gripper.activate()
        assert gripper.is_activated() is True

        robot = _make_robot(gripper=gripper)
        robot.disconnect()
        robot._motion.stop_script.assert_called_once()

    def test_disconnect_skips_stop_script_while_activation_in_progress(self):
        """An in-flight activation thread (e.g. after a timeout raised)
        also triggers the guard."""
        rtde_c = MagicMock()
        rtde_r = MagicMock()

        def slow_send(name, code):
            time.sleep(2.0)
            return True

        rtde_c.sendCustomScriptFunction.side_effect = slow_send
        gripper = RobotiqGripper(rtde_control=rtde_c, rtde_receive=rtde_r)

        t = threading.Thread(
            target=gripper.activate, kwargs={"timeout": 10.0}
        )
        t.start()
        try:
            # Wait until the daemon thread is inside the (slow) send.
            time.sleep(0.3)
            assert gripper._activation_running is True
            robot = _make_robot(gripper=gripper)
            robot.disconnect()  # must not hang in stopScript()
            robot._motion.stop_script.assert_not_called()
        finally:
            t.join(10.0)


class TestActivateGripperFailureFlag:

    def test_failure_sets_flag_and_nulls_gripper(self):
        """_activate_gripper() records the failure so a later
        disconnect() skips stopScript(), and disables the gripper for
        the session."""
        robot = _make_robot(gripper=_failed_activation_gripper())
        assert robot._activate_gripper() is False
        assert robot._gripper_activation_failed is True
        assert robot._gripper is None
        # And disconnect() honors the flag.
        robot.disconnect()
        robot._motion.stop_script.assert_not_called()

    def test_success_clears_flag(self):
        rtde_c = MagicMock()
        rtde_r = MagicMock()
        gripper = RobotiqGripper(rtde_control=rtde_c, rtde_receive=rtde_r)
        robot = _make_robot(gripper=gripper)
        assert robot._activate_gripper() is True
        assert robot._gripper_activation_failed is False
        assert robot._gripper is gripper
