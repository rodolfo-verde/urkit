"""Unit tests for move_sequence with ik_reference and blending.

Tests the IK resolution, path building, and blending logic
without requiring a real robot.
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pytest

from urkit.exceptions import MotionError, PointError
from urkit.points import Point, Points


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture
def mock_rtde_c():
    """Mock RTDEControlInterface."""
    mock = MagicMock()
    mock.isConnected.return_value = True
    mock.getInverseKinematicsHasSolution.return_value = True
    mock.getInverseKinematics.return_value = [0.0, -0.5, 0.5, -1.5, 1.5, 0.0]
    return mock


@pytest.fixture
def mock_rtde_r():
    """Mock RTDEReceiveInterface."""
    mock = MagicMock()
    mock.getActualQ.return_value = [0.0, -1.0, 1.0, -1.57, 1.57, 0.0]
    mock.getActualTCPPose.return_value = [0.5, 0.0, 0.3, 0.0, 0.0, 0.0]
    return mock


@pytest.fixture
def mock_points(tmp_path):
    """Create a temporary points database with test data."""
    db_path = tmp_path / "test_points.db"
    pts = Points(db_path)
    pts.save(Point(name="home", pose=[0.5, 0.0, 0.3, 0.0, 0.0, 0.0]))
    pts.save(Point(name="pick", pose=[0.3, 0.2, 0.1, 0.0, 0.0, 0.0]))
    pts.save(Point(name="place", pose=[0.3, -0.2, 0.1, 0.0, 0.0, 0.0]))
    return pts


@pytest.fixture
def robot(mock_rtde_c, mock_rtde_r, mock_points, tmp_path):
    """Create a URRobot with mocked RTDE interfaces."""
    with patch("urkit.robot._validate_connection"), \
         patch("urkit.robot._check_remote_mode"), \
         patch("urkit.robot._connect_rtde") as mock_connect, \
         patch("urkit.robot._connect_dashboard"), \
         patch("urkit.robot._try_recover_safety"):
        
        # Set up the connect mock to populate rtde interfaces
        mock_connect.return_value = (mock_rtde_c, mock_rtde_r)
        
        from urkit.robot import URRobot
        robot = object.__new__(URRobot)  # bypass __init__
        robot._ip = "127.0.0.1"
        robot._rtde_c = mock_rtde_c
        robot._rtde_r = mock_rtde_r
        robot._rtde_frequency = 500.0
        robot._connection_lost = False
        robot._default_vel = 0.5
        robot._default_acc = 0.3
        robot._points = mock_points
        robot._move_frame = None
        robot._move_target_joints = None
        robot._ik_reference = None
        
        # Mock the motion object
        robot._motion = MagicMock()
        
        # Mock _check_connection and _disable_freedrive_guard
        robot._check_connection = MagicMock()
        robot._disable_freedrive_guard = MagicMock()
        
        # Mock inverse_kinematics to delegate to rtde_c
        original_ik = robot.inverse_kinematics.__func__ if hasattr(robot.inverse_kinematics, '__func__') else None
        
        def mock_ik(pose, seed=None):
            qnear = seed if seed is not None else []
            if not mock_rtde_c.getInverseKinematicsHasSolution(pose, qnear):
                raise MotionError(f"No IK solution for pose {pose}")
            return mock_rtde_c.getInverseKinematics(pose, qnear)
        
        # Bind mock_ik to the robot instance
        import types
        robot.inverse_kinematics = types.MethodType(
            lambda self, pose, seed=None: mock_ik(pose, seed), robot
        )
        
        return robot


# ------------------------------------------------------------------
# Tests: _resolve_ik_reference
# ------------------------------------------------------------------


class TestResolveIkReference:
    """Test the _resolve_ik_reference helper method."""

    def test_current_returns_actual_joints(self, robot, mock_rtde_r):
        result = robot._resolve_ik_reference("current")
        assert result == list(mock_rtde_r.getActualQ())

    def test_point_name_resolves_to_joints(self, robot, mock_rtde_c):
        """Named point should be looked up and resolved via IK."""
        result = robot._resolve_ik_reference("home")
        # Should call inverse_kinematics with the point's pose
        assert len(result) == 6
        # The mock returns the default IK result
        assert result == [0.0, -0.5, 0.5, -1.5, 1.5, 0.0]

    def test_missing_point_falls_back_to_current(self, robot, mock_rtde_r, caplog):
        """Non-existent point name should fall back to current joints."""
        with caplog.at_level(logging.WARNING):
            result = robot._resolve_ik_reference("nonexistent")
        assert result == list(mock_rtde_r.getActualQ())
        assert "point not found" in caplog.text or "falling back" in caplog.text

    def test_joints_list_used_directly(self, robot):
        """Raw joint list should be returned as-is."""
        joints = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6]
        result = robot._resolve_ik_reference(joints)
        assert result == joints

    def test_no_points_db_falls_back(self, robot, mock_rtde_r, caplog):
        """When points DB is None, should fall back to current joints."""
        robot._points = None
        result = robot._resolve_ik_reference("home")
        assert result == list(mock_rtde_r.getActualQ())


# ------------------------------------------------------------------
# Tests: move_sequence validation
# ------------------------------------------------------------------


class TestMoveSequenceValidation:
    """Test move_sequence input validation."""

    def test_requires_at_least_two_targets(self, robot):
        with pytest.raises(MotionError, match="at least 2"):
            robot.move_sequence(["single_point"])

    def test_empty_targets_raises(self, robot):
        with pytest.raises(MotionError, match="at least 2"):
            robot.move_sequence([])


# ------------------------------------------------------------------
# Tests: move_sequence legacy mode (no ik_reference)
# ------------------------------------------------------------------


class TestMoveSequenceLegacy:
    """Test move_sequence without ik_reference (legacy behavior)."""

    def test_linear_mode_calls_movel(self, robot, mock_rtde_c):
        """Without ik_reference and linear=True, should call moveL."""
        robot.move_sequence(["home", "pick"])
        # Should have called moveL twice (once per target)
        assert mock_rtde_c.moveL.call_count == 2

    def test_joints_mode_calls_movej_ik(self, robot, mock_rtde_c):
        """Without ik_reference and linear=False, should call moveJ_IK."""
        robot.move_sequence(["home", "pick"], linear=False)
        assert mock_rtde_c.moveJ_IK.call_count == 2

    def test_raw_poses_work(self, robot, mock_rtde_c):
        """Raw pose lists should work as targets."""
        poses = [
            [0.5, 0.0, 0.3, 0.0, 0.0, 0.0],
            [0.3, 0.2, 0.1, 0.0, 0.0, 0.0],
        ]
        robot.move_sequence(poses)
        assert mock_rtde_c.moveL.call_count == 2


# ------------------------------------------------------------------
# Tests: move_sequence with ik_reference
# ------------------------------------------------------------------


class TestMoveSequenceWithIkReference:
    """Test move_sequence with ik_reference for IK stability."""

    def test_ik_reference_resolves_path(self, robot, mock_rtde_c):
        """With ik_reference, should call moveJ(path) once."""
        robot.move_sequence(["home", "pick", "place"], ik_reference="current")
        # Should call moveJ once with a path (not individual moveL)
        assert mock_rtde_c.moveJ.call_count == 1
        # moveL should NOT be called
        assert mock_rtde_c.moveL.call_count == 0

    def test_path_format_is_nine_elements(self, robot, mock_rtde_c):
        """Each waypoint in the path should have 9 elements."""
        robot.move_sequence(["home", "pick"], ik_reference="current")
        call_args = mock_rtde_c.moveJ.call_args
        path = call_args[0][0]  # first positional arg
        assert len(path) == 2  # two waypoints
        for waypoint in path:
            assert len(waypoint) == 9  # [j0..j5, vel, acc, blend]

    def test_last_waypoint_has_zero_blend(self, robot, mock_rtde_c):
        """Last waypoint should have blend_radius=0 (come to rest)."""
        robot.move_sequence(
            ["home", "pick", "place"],
            ik_reference="current",
            blend_radius=0.02,
        )
        path = mock_rtde_c.moveJ.call_args[0][0]
        # Last waypoint blend should be 0
        assert path[-1][8] == 0.0
        # Intermediate waypoints should have the blend radius
        assert path[0][8] == 0.02

    def test_chained_ik_calls(self, robot, mock_rtde_c):
        """IK should be called once per target (chained)."""
        # Reset the call count
        mock_rtde_c.getInverseKinematics.reset_mock()
        
        robot.move_sequence(["home", "pick", "place"], ik_reference="current")
        
        # 3 targets = 3 IK calls (each chained from previous)
        assert mock_rtde_c.getInverseKinematics.call_count == 3

    def test_ik_reference_point_name(self, robot, mock_rtde_c):
        """ik_reference as a point name should resolve via IK."""
        robot.move_sequence(["pick", "place"], ik_reference="home")
        assert mock_rtde_c.moveJ.call_count == 1

    def test_ik_reference_joints_list(self, robot, mock_rtde_c):
        """ik_reference as a raw joints list should work."""
        ref_joints = [0.0, -1.0, 1.0, -1.57, 1.57, 0.0]
        robot.move_sequence(["pick", "place"], ik_reference=ref_joints)
        assert mock_rtde_c.moveJ.call_count == 1

    def test_async_passed_through(self, robot, mock_rtde_c):
        """asynchronous parameter should be passed to moveJ(path)."""
        robot.move_sequence(
            ["home", "pick"],
            ik_reference="current",
            asynchronous=True,
        )
        call_kwargs = mock_rtde_c.moveJ.call_args[1]
        assert call_kwargs.get("asynchronous") is True

    def test_vel_acc_in_path(self, robot, mock_rtde_c):
        """Velocity and acceleration should be in each path waypoint."""
        robot.move_sequence(
            ["home", "pick"],
            ik_reference="current",
            vel=0.8,
            acc=0.5,
        )
        path = mock_rtde_c.moveJ.call_args[0][0]
        for waypoint in path:
            assert waypoint[6] == 0.8  # velocity
            assert waypoint[7] == 0.5  # acceleration

    def test_defaults_used_when_no_vel_acc(self, robot, mock_rtde_c):
        """Default vel/acc should be used when not specified."""
        robot._default_vel = 0.5
        robot._default_acc = 0.3
        robot.move_sequence(["home", "pick"], ik_reference="current")
        path = mock_rtde_c.moveJ.call_args[0][0]
        for waypoint in path:
            assert waypoint[6] == 0.5
            assert waypoint[7] == 0.3

    def test_global_ik_reference_used_when_not_specified(self, robot, mock_rtde_c):
        """When ik_reference is not specified, should use global setting."""
        robot._ik_reference = "home"
        mock_rtde_c.getInverseKinematics.reset_mock()
        robot.move_sequence(["pick", "place"])  # no ik_reference arg
        # Should use global ik_reference and call moveJ(path)
        assert mock_rtde_c.moveJ.call_count == 1
        assert mock_rtde_c.getInverseKinematics.call_count >= 2

    def test_per_call_overrides_global(self, robot, mock_rtde_c):
        """Per-call ik_reference=None should override global setting."""
        robot._ik_reference = "home"
        robot.move_sequence(["pick", "place"], ik_reference=None)
        # Should use legacy mode (individual moveL)
        assert mock_rtde_c.moveL.call_count == 2
