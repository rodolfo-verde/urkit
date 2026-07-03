"""Integration tests against a real Universal Robot.

Set ROBOT_IP environment variable to run:
    ROBOT_IP=192.168.1.50 PYTHONPATH= .venv/bin/python -m pytest tests/test_robot_integration.py -v

Tests are skipped automatically if ROBOT_IP is not set or the robot
is unreachable. All tests are designed to be safe — read-only telemetry
queries, small motion moves that return to the original position, and
proper cleanup after each test.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from urkit.exceptions import MotionError, PointError
from urkit.robot import URRobot


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _robot_ip() -> str | None:
    """Get robot IP from environment or config."""
    ip = os.environ.get("ROBOT_IP")
    if ip:
        return ip
    # Fall back to config file
    try:
        from urkit.config import load_config

        cfg = load_config()
        return cfg.get("robot_ip")
    except Exception:
        return None


@pytest.fixture(scope="module")
def robot():
    """Connect to a real robot for the test module.

    Skips all tests if ROBOT_IP is not set or connection fails.
    The robot is properly disconnected after all tests complete.
    """
    ip = _robot_ip()
    if not ip:
        pytest.skip("ROBOT_IP not set (set environment variable or config robot_ip)")

    # Create a temporary points database for tests
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    points_path = tmp.name
    tmp.close()

    try:
        r = URRobot(ip=ip, points=points_path)
    except Exception as e:
        pytest.skip(f"Failed to connect to robot at {ip}: {e}")

    yield r
    r.disconnect()


# ------------------------------------------------------------------
# Telemetry tests (read-only, safe)
# ------------------------------------------------------------------


class TestTelemetry:
    """Test telemetry reads against a real robot."""

    def test_tcp_pose_returns_list(self, robot):
        pose = robot.get_tcp_pose()
        assert isinstance(pose, list)
        assert len(pose) == 6
        assert all(isinstance(v, (int, float)) for v in pose)

    def test_joint_positions_returns_list(self, robot):
        joints = robot.get_joint_positions()
        assert isinstance(joints, list)
        assert len(joints) == 6
        assert all(isinstance(v, (int, float)) for v in joints)

    def test_tcp_force_returns_list(self, robot):
        force = robot.get_tcp_force()
        assert isinstance(force, list)
        assert len(force) == 6

    def test_robot_mode_returns_string(self, robot):
        mode = robot.get_robot_mode()
        assert isinstance(mode, str)
        assert len(mode) > 0

    def test_payload_returns_float(self, robot):
        payload = robot.get_payload()
        assert isinstance(payload, (int, float))
        assert payload >= 0

    def test_current_point(self, robot):
        pos = robot.current_point()
        assert isinstance(pos, dict)
        assert "pose" in pos
        assert "joints" in pos
        assert len(pos["pose"]) == 6
        assert len(pos["joints"]) == 6

    def test_protective_stop_boolean(self, robot):
        stopped = robot.is_protective_stopped()
        assert isinstance(stopped, bool)


# ------------------------------------------------------------------
# I/O tests (read-only where possible)
# ------------------------------------------------------------------


class TestIO:
    """Test I/O operations against a real robot."""

    def test_digital_input_returns_bool(self, robot):
        val = robot.get_digital_input(0)
        assert isinstance(val, bool)

    def test_tool_input_returns_bool(self, robot):
        val = robot.get_tool_input(0)
        assert isinstance(val, bool)

    def test_tool_output_returns_bool(self, robot):
        val = robot.get_tool_output(0)
        assert isinstance(val, bool)

    def test_analog_input_returns_number(self, robot):
        val = robot.get_analog_input(0)
        assert isinstance(val, (int, float))

    def test_analog_output_returns_number(self, robot):
        val = robot.get_analog_output(0)
        assert isinstance(val, (int, float))

    def test_tool_input_invalid_pin(self, robot):
        with pytest.raises(Exception, match="0"):
            robot.get_tool_input(2)

    def test_tool_output_invalid_pin(self, robot):
        with pytest.raises(Exception, match="0"):
            robot.get_tool_output(5)

    def test_analog_input_invalid_pin(self, robot):
        with pytest.raises(Exception, match="0"):
            robot.get_analog_input(2)

    def test_analog_output_invalid_pin(self, robot):
        with pytest.raises(Exception, match="0"):
            robot.get_analog_output(5)


# ------------------------------------------------------------------
# Motion validation tests (no actual motion)
# ------------------------------------------------------------------


class TestMotionValidation:
    """Test motion input validation without moving the robot."""

    def test_move_relative_wrong_count(self, robot):
        with pytest.raises(MotionError, match="6 values"):
            robot.move_relative([1, 2, 3])

    def test_tcp_offset_wrong_count(self, robot):
        with pytest.raises(MotionError, match="6 values"):
            robot.set_tcp_offset([1, 2, 3])

    def test_payload_negative(self, robot):
        with pytest.raises(MotionError, match=">= 0"):
            robot.set_payload(-1)

    def test_speed_slider_invalid(self, robot):
        with pytest.raises(MotionError):
            robot.set_speed_slider(1.5)

    def test_inverse_kinematics_unreachable_raises(self, robot):
        # Pose far outside any robot's workspace
        unreachable = [10.0, 10.0, 10.0, 0, 0, 0]
        with pytest.raises(MotionError, match="No IK solution"):
            robot.inverse_kinematics(unreachable)

    def test_inverse_kinematics_current_pose(self, robot):
        # IK of current pose should return joints close to current joints
        current = robot.current_point()
        joints = robot.inverse_kinematics(current["pose"], seed=current["joints"])
        assert len(joints) == 6
        # Should be very close to seed
        for a, b in zip(joints, current["joints"]):
            assert abs(a - b) < 0.1


# ------------------------------------------------------------------
# Properties
# ------------------------------------------------------------------


class TestProperties:
    """Test URRobot properties."""

    def test_ip_property(self, robot):
        assert robot.ip == _robot_ip()

    def test_freedrive_inactive_by_default(self, robot):
        assert robot.is_freedrive_active is False

    def test_connection_lost_false(self, robot):
        assert robot.connection_lost is False


# ------------------------------------------------------------------
# Motion tests (small safe moves)
# ------------------------------------------------------------------


class TestMotion:
    """Test actual motion commands with small safe moves.

    Each move is tiny (1mm) and returns to the original position.
    """

    def test_move_relative_linear(self, robot):
        """Test a tiny linear move and return."""
        original = robot.get_tcp_pose()
        robot.move_relative([0, 0.001, 0, 0, 0, 0], vel=0.1, acc=0.1)
        robot.move_relative([0, -0.001, 0, 0, 0, 0], vel=0.1, acc=0.1)
        # Robot should be close to original position
        current = robot.get_tcp_pose()
        assert abs(current[1] - original[1]) < 0.005

    def test_speed_slider(self, robot):
        """Test setting speed slider."""
        robot.set_speed_slider(0.5)
        robot.set_speed_slider(1.0)  # Reset

    def test_connection_lost_raises(self, robot):
        """Test that motion fails when connection is lost."""
        robot._connection_lost = True
        with pytest.raises(Exception):
            robot.move_relative([0, 0, 0, 0, 0, 0])
        robot._connection_lost = False  # Reset


# ------------------------------------------------------------------
# Motion constructor validation
# ------------------------------------------------------------------


class TestMotionConstructor:
    """Test Motion class validation."""

    def test_motion_negative_velocity_raises(self):
        from urkit.motion import Motion

        with pytest.raises(MotionError, match="> 0"):
            Motion(None, None, None, default_vel=-1)  # type: ignore

    def test_motion_zero_acceleration_raises(self):
        from urkit.motion import Motion

        with pytest.raises(MotionError, match="> 0"):
            Motion(None, None, None, default_acc=0)  # type: ignore


# ------------------------------------------------------------------
# Point management tests
# ------------------------------------------------------------------


class TestPointManagement:
    """Test point management methods on URRobot."""

    def test_save_and_lookup_point(self, robot):
        """Test saving and looking up a point by name."""
        robot.save_point("test_point")
        names = robot.point_names()
        assert "test_point" in names

    def test_point_names_sorted(self, robot):
        """Test that point_names returns sorted list."""
        robot.save_point("charlie")
        robot.save_point("alpha")
        robot.save_point("bravo")
        names = robot.point_names()
        # Should be sorted (may include test_point from above)
        assert names == sorted(names)

    def test_delete_point(self, robot):
        """Test deleting a point."""
        robot.save_point("to_delete")
        assert "to_delete" in robot.point_names()
        robot.delete_point("to_delete")
        assert "to_delete" not in robot.point_names()

    def test_delete_missing_point_raises(self, robot):
        """Test that deleting a missing point raises KeyError."""
        with pytest.raises(KeyError):
            robot.delete_point("nonexistent_point_xyz")

    def test_move_to_named_point(self, robot):
        """Test moving to a named point."""
        # Save current position as a point
        robot.save_point("move_test")
        # Moving to it should not raise (robot is already there)
        # Use vel=0.1 for safety
        robot.move_to("move_test", vel=0.1, acc=0.1)

    def test_move_to_raw_pose(self, robot):
        """Test moving to a raw pose (current position)."""
        current = robot.get_tcp_pose()
        # Moving to current pose should not raise
        robot.move_to(current, vel=0.1, acc=0.1)

    def test_move_to_missing_point_raises(self, robot):
        """Test that moving to a missing point raises PointError."""
        with pytest.raises(PointError, match="not found"):
            robot.move_to("nonexistent_point_xyz")

    def test_move_to_with_offset(self, robot):
        """Test moving to a point with offset."""
        robot.save_point("offset_test")
        # Small offset from current position
        robot.move_to("offset_test", offset=[0, 0, 0.001, 0, 0, 0], vel=0.1, acc=0.1)

    def test_export_import_points(self, robot, tmp_path):
        """Test exporting and importing points."""
        robot.save_point("export_test")
        json_path = tmp_path / "test_points.json"
        robot.export_points(json_path)
        assert json_path.exists()

        # Import into a new temp database
        import_path = tmp_path / "import_test.db"
        from urkit.points import Points
        pts = Points(import_path)
        pts.import_json(json_path)
        assert "export_test" in pts.list()
        pts._close()
