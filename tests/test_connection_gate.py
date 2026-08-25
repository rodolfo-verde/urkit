"""Tests for the pre-motion connection gate (_check_connection).

A call into the C++ layer on a dead RTDE link does not return an
error: ur_rtde enters an internal reconnect loop and blocks
indefinitely. The gate must fail fast, before the native call, with an
actionable error, and mark the session dead for good.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from urkit.exceptions import URKitConnectionError


@pytest.fixture
def robot(mock_rtde_c=None) -> object:
    """URRobot with mocked RTDE interfaces, bypassing __init__."""
    rtde_c = MagicMock()
    rtde_c.isConnected.return_value = True
    rtde_c.getInverseKinematicsHasSolution.return_value = True
    rtde_c.getInverseKinematics.return_value = [0.0, -0.5, 0.5, -1.5, 1.5, 0.0]
    rtde_r = MagicMock()
    rtde_r.getActualQ.return_value = [0.0, -1.0, 1.0, -1.57, 1.57, 0.0]
    rtde_r.getActualTCPPose.return_value = [0.5, 0.0, 0.3, 0.0, 0.0, 0.0]

    from urkit.robot import URRobot

    r = object.__new__(URRobot)
    r._ip = "127.0.0.1"
    r._rtde_c = rtde_c
    r._rtde_r = rtde_r
    r._rtde_frequency = 500.0
    r._connection_lost = False
    r._default_vel = 0.5
    r._default_acc = 0.3
    r._points = None
    r._move_frame = None
    r._move_target_pose = None
    r._move_target_joints = None
    r._ik_reference = None
    r._freedrive_active = False
    r._motion = MagicMock()
    r._motion.is_freedrive_active = False
    r._gripper = None
    r._dashboard = None
    return r


class TestConnectionGate:
    def test_dead_link_blocks_move_relative(self, robot):
        robot._rtde_c.isConnected.return_value = False
        with pytest.raises(URKitConnectionError, match="RTDE link"):
            robot.move_relative(dy=-0.005)
        # The native call must never be reached.
        robot._rtde_c.moveL.assert_not_called()
        robot._rtde_c.moveJ.assert_not_called()

    def test_dead_link_blocks_move_to(self, robot):
        robot._rtde_c.isConnected.return_value = False
        with pytest.raises(URKitConnectionError, match="RTDE link"):
            robot.move_to([0.5, 0.0, 0.3, 0.0, 0.0, 0.0])
        robot._rtde_c.moveL.assert_not_called()

    def test_dead_link_flags_session_dead(self, robot):
        robot._rtde_c.isConnected.return_value = False
        with pytest.raises(URKitConnectionError):
            robot.move_relative(dy=-0.005)
        assert robot.connection_lost is True

    def test_flag_blocks_even_if_socket_reports_back(self, robot):
        # Once the session is flagged dead it stays dead for the
        # process lifetime, even if the C++ socket claims to be back
        # (a mid-flight reconnect is not a safe recovery path).
        robot._connection_lost = True
        robot._rtde_c.isConnected.return_value = True
        with pytest.raises(URKitConnectionError, match="reinitialized"):
            robot.move_relative(dy=-0.005)
        robot._rtde_c.moveL.assert_not_called()

    def test_live_link_passes_gate(self, robot):
        # With a live link the gate must not interfere: the native
        # call is reached (mocked _motion layer absorbs the rest).
        robot._rtde_c.moveL.return_value = True
        robot._rtde_c.moveJ.return_value = True
        robot._motion.moveL = MagicMock(return_value=True)
        try:
            robot.move_relative(dy=-0.005)
        except Exception:
            # Downstream mock gaps are fine; the gate itself must not
            # have raised.
            pass
        assert robot.connection_lost is False

    def test_stop_is_not_gated(self, robot):
        # Cleanup calls (stop, speed_stop) must keep working on a dead
        # link: they are best-effort and swallow native failures.
        robot._rtde_c.isConnected.return_value = False
        robot._rtde_c.stopL.side_effect = OSError("[WinError 1] Incorrect function")
        robot._rtde_c.stopJ.side_effect = OSError("[WinError 1] Incorrect function")
        robot.stop()  # must not raise
        robot.speed_stop()
