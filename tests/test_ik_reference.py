"""Tests for the GLOBAL ik_reference sentinel (move_to, move_sequence).

The ik_reference parameter has three states:

- GLOBAL (default): use the robot's global ik_reference setting
- None: disable the IK reference for one move
- a point name or 6-joint list: explicit per-call reference

The previous "__global__" magic string must fail loud with a
migration hint, and the sentinel must be matched by identity so a
foreign instance of the private class is never treated as GLOBAL.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import urkit
from urkit.exceptions import MotionError
from urkit.robot import GLOBAL, URRobot, _GlobalIKReference

POSE = [0.5, 0.0, 0.3, 0.0, 0.0, 0.0]
GLOBAL_SETTING = "home"
RESOLVED_JOINTS = [10.0] * 6


@pytest.fixture
def robot() -> URRobot:
    """URRobot with mocked RTDE, points, and IK seams.

    _resolve_ik_reference is spied on so tests can assert exactly
    which effective reference each state resolves to, without a real
    points DB or IK solver.
    """
    rtde_c = MagicMock()
    rtde_c.isConnected.return_value = True
    rtde_c.getInverseKinematicsHasSolution.return_value = True
    rtde_r = MagicMock()
    rtde_r.getActualQ.return_value = [0.0] * 6

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
    r._ik_reference = GLOBAL_SETTING
    r._freedrive_active = False
    r._motion = MagicMock()
    r._motion.is_freedrive_active = False
    r._gripper = None
    r._dashboard = None

    # IK seams: record what the effective reference resolves to.
    point = SimpleNamespace(pose=POSE, with_delta=MagicMock())
    r._lookup_point = MagicMock(return_value=point)
    r._resolve_ik_reference = MagicMock(return_value=RESOLVED_JOINTS)
    r.inverse_kinematics = MagicMock(return_value=[1.0] * 6)
    return r


class TestSentinel:
    def test_repr(self) -> None:
        assert repr(GLOBAL) == "GLOBAL"

    def test_package_export_is_identity(self) -> None:
        # Users get the same singleton no matter how they import it.
        assert urkit.GLOBAL is GLOBAL
        assert "GLOBAL" in urkit.__all__

    def test_foreign_instance_is_not_global(self, robot: URRobot) -> None:
        # Identity semantics: a constructed instance of the private
        # class must NOT be treated as the sentinel. It falls through
        # to explicit-reference handling instead of the global setting.
        impostor = _GlobalIKReference()
        robot.move_to("p", linear=False, ik_reference=impostor)
        robot._resolve_ik_reference.assert_called_once_with(impostor)


class TestGlobalSetting:
    """The global ik_reference setting (constructor, config, property)
    rejects per-call values at assignment time, with no fallback:
    a bad value must not sit in the robot and fail later as a
    point-lookup error or the current-joints warning."""

    def test_rejects_old_string(self, robot: URRobot) -> None:
        with pytest.raises(MotionError, match="__global__"):
            robot.ik_reference = "__global__"
        # No silent fallback: the previous value is kept.
        assert robot.ik_reference == GLOBAL_SETTING

    def test_rejects_global_sentinel(self, robot: URRobot) -> None:
        with pytest.raises(MotionError, match="per-call"):
            robot.ik_reference = GLOBAL
        assert robot.ik_reference == GLOBAL_SETTING

    @pytest.mark.parametrize(
        "value",
        ["home", "current", [0.0, 1.0, 2.0, 3.0, 4.0, 5.0], None],
    )
    def test_accepts_valid_values(self, robot: URRobot, value: object) -> None:
        robot.ik_reference = value
        assert robot.ik_reference == value


class TestMoveTo:
    def test_default_uses_global_setting(self, robot: URRobot) -> None:
        robot.move_to("p", linear=False)
        robot._resolve_ik_reference.assert_called_once_with(GLOBAL_SETTING)

    def test_global_uses_global_setting(self, robot: URRobot) -> None:
        robot.move_to("p", linear=False, ik_reference=GLOBAL)
        robot._resolve_ik_reference.assert_called_once_with(GLOBAL_SETTING)

    def test_global_with_unset_global_setting_passes_none(self, robot: URRobot) -> None:
        robot._ik_reference = None
        robot.move_to("p", linear=False, ik_reference=GLOBAL)
        robot._resolve_ik_reference.assert_not_called()
        robot.inverse_kinematics.assert_called_once_with(POSE, seed=None)

    def test_none_disables_for_one_move(self, robot: URRobot) -> None:
        robot.move_to("p", linear=False, ik_reference=None)
        robot._resolve_ik_reference.assert_not_called()
        robot.inverse_kinematics.assert_called_once_with(POSE, seed=None)

    def test_explicit_name_overrides_global(self, robot: URRobot) -> None:
        robot.move_to("p", linear=False, ik_reference="other")
        robot._resolve_ik_reference.assert_called_once_with("other")

    def test_explicit_joint_list(self, robot: URRobot) -> None:
        joints = [0.1, -0.2, 0.3, -1.0, 1.5, 0.0]
        robot.move_to("p", linear=False, ik_reference=joints)
        robot._resolve_ik_reference.assert_called_once_with(joints)

    def test_old_magic_string_fails_loud(self, robot: URRobot) -> None:
        with pytest.raises(MotionError, match="urkit.GLOBAL"):
            robot.move_to("p", linear=False, ik_reference="__global__")
        robot._resolve_ik_reference.assert_not_called()

    def test_explicit_with_linear_raises(self, robot: URRobot) -> None:
        with pytest.raises(MotionError, match="linear=False"):
            robot.move_to("p", linear=True, ik_reference="other")
        robot._motion.movel.assert_not_called()

    def test_global_with_linear_is_allowed(self, robot: URRobot) -> None:
        # GLOBAL + linear is not a contradiction: linear moves simply
        # ignore the reference.
        robot.move_to("p", linear=True, ik_reference=GLOBAL)
        robot._motion.movel.assert_called_once()

    def test_none_with_linear_is_allowed(self, robot: URRobot) -> None:
        robot.move_to("p", linear=True, ik_reference=None)
        robot._motion.movel.assert_called_once()

    def test_default_with_linear_is_allowed(self, robot: URRobot) -> None:
        robot.move_to("p", linear=True)
        robot._motion.movel.assert_called_once()


class TestMoveSequence:
    def test_default_uses_global_setting(self, robot: URRobot) -> None:
        robot.move_sequence("a", "b", linear=False)
        robot._resolve_ik_reference.assert_called_once_with(GLOBAL_SETTING)

    def test_global_uses_global_setting(self, robot: URRobot) -> None:
        robot.move_sequence("a", "b", linear=False, ik_reference=GLOBAL)
        robot._resolve_ik_reference.assert_called_once_with(GLOBAL_SETTING)

    def test_none_disables(self, robot: URRobot) -> None:
        robot.move_sequence("a", "b", linear=False, ik_reference=None)
        robot._resolve_ik_reference.assert_not_called()
        # Both poses resolve independently with no seed.
        assert robot.inverse_kinematics.call_count == 2
        for call in robot.inverse_kinematics.call_args_list:
            assert call.kwargs["seed"] is None

    def test_explicit_name_overrides_global(self, robot: URRobot) -> None:
        robot.move_sequence("a", "b", linear=False, ik_reference="other")
        robot._resolve_ik_reference.assert_called_once_with("other")

    def test_chaining_uses_previous_joints(self, robot: URRobot) -> None:
        # The reference chains: pose 2 seeds from pose 1's resolved
        # joints, not from the original reference.
        robot.inverse_kinematics.side_effect = [[1.0] * 6, [2.0] * 6]
        robot.move_sequence("a", "b", linear=False, ik_reference=GLOBAL)
        first, second = robot.inverse_kinematics.call_args_list
        assert first.kwargs["seed"] == RESOLVED_JOINTS
        assert second.kwargs["seed"] == [1.0] * 6

    def test_old_magic_string_fails_loud(self, robot: URRobot) -> None:
        with pytest.raises(MotionError, match="urkit.GLOBAL"):
            robot.move_sequence("a", "b", linear=False, ik_reference="__global__")
        robot._rtde_c.moveJ.assert_not_called()

    def test_explicit_with_linear_raises(self, robot: URRobot) -> None:
        with pytest.raises(MotionError, match="linear=False"):
            robot.move_sequence("a", "b", linear=True, ik_reference="other")
        robot._rtde_c.moveL.assert_not_called()

    def test_global_with_linear_is_allowed(self, robot: URRobot) -> None:
        robot.move_sequence("a", "b", linear=True, ik_reference=GLOBAL)
        robot._rtde_c.moveL.assert_called_once()
        # Linear path rows are 9-element [pose, vel, acc, blend].
        path = robot._rtde_c.moveL.call_args[0][0]
        assert len(path) == 2
        assert all(len(row) == 9 for row in path)
