"""Tests for held payload (set_held_payload) and physical overrides.

Held payload lets a caller add the mass of a picked-up object to the
payload (for gravity compensation) and reset it to the base payload
with mass=0. Physical overrides (mass/center_of_gravity/tcp_offset)
must be popped from gripper_kwargs before backend construction.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from urkit.exceptions import MotionError
from urkit.gripper.presets import (
    ROBOTIQ_EPICK_SINGLE_S,
    DigitalGripperConfig,
)
from urkit.robot import URRobot, _apply_physical_overrides

BASE_MASS = 0.736
BASE_COG = [0.0, 0.0, 0.0547]
TCP_OFFSET = [0.0, 0.0, 0.145, 0.0, 0.0, 0.0]


@pytest.fixture
def robot() -> URRobot:
    """URRobot with mocked RTDE, bypassing __init__ (held payload state)."""
    rtde_c = MagicMock()
    rtde_c.getTCPOffset.return_value = list(TCP_OFFSET)

    r = object.__new__(URRobot)
    r._ip = "127.0.0.1"
    r._rtde_c = rtde_c
    r._rtde_r = MagicMock()
    r._payload = BASE_MASS
    r._base_payload = BASE_MASS
    r._base_cog = list(BASE_COG)
    r._held_payload = 0.0
    return r


class TestSetHeldPayload:
    def test_adds_to_base_with_weighted_cog(self, robot: URRobot) -> None:
        robot.set_held_payload(0.05, center_of_gravity=[0.0, 0.0, 0.113])
        mass, cog, _inertia = robot._rtde_c.setTargetPayload.call_args[0]
        assert mass == pytest.approx(BASE_MASS + 0.05)
        expected_z = (BASE_MASS * BASE_COG[2] + 0.05 * 0.113) / (BASE_MASS + 0.05)
        assert cog[2] == pytest.approx(expected_z)
        assert robot.held_payload == 0.05
        assert robot.payload == pytest.approx(BASE_MASS + 0.05)

    def test_default_cog_is_tcp_position(self, robot: URRobot) -> None:
        robot.set_held_payload(0.05)
        mass, cog, _inertia = robot._rtde_c.setTargetPayload.call_args[0]
        expected_z = (
            BASE_MASS * BASE_COG[2] + 0.05 * TCP_OFFSET[2]
        ) / (BASE_MASS + 0.05)
        assert cog[2] == pytest.approx(expected_z)

    def test_zero_resets_to_base_not_zero(self, robot: URRobot) -> None:
        robot.set_held_payload(0.05)
        robot.set_held_payload(0)
        mass, cog, _inertia = robot._rtde_c.setTargetPayload.call_args[0]
        assert mass == pytest.approx(BASE_MASS)
        assert cog == BASE_COG
        assert robot.held_payload == 0.0

    def test_replaces_not_accumulates(self, robot: URRobot) -> None:
        robot.set_held_payload(0.05)
        robot.set_held_payload(0.08)
        mass, _cog, _inertia = robot._rtde_c.setTargetPayload.call_args[0]
        assert mass == pytest.approx(BASE_MASS + 0.08)
        assert robot.held_payload == 0.08

    def test_zero_base_payload(self, robot: URRobot) -> None:
        robot._base_payload = 0.0
        robot._base_cog = [0.0, 0.0, 0.0]
        robot.set_held_payload(0.05, center_of_gravity=[0.0, 0.0, 0.2])
        mass, cog, _inertia = robot._rtde_c.setTargetPayload.call_args[0]
        assert mass == pytest.approx(0.05)
        assert cog == [0.0, 0.0, 0.2]

    def test_negative_raises(self, robot: URRobot) -> None:
        with pytest.raises(MotionError, match=">= 0"):
            robot.set_held_payload(-0.1)

    def test_bad_cog_raises(self, robot: URRobot) -> None:
        with pytest.raises(MotionError, match="3 values"):
            robot.set_held_payload(0.05, center_of_gravity=[0.0, 0.0])

    def test_set_payload_while_held_raises(self, robot: URRobot) -> None:
        robot.set_held_payload(0.05)
        with pytest.raises(MotionError, match="held"):
            robot.set_payload(2.0, [0.0, 0.0, 0.1])

    def test_set_payload_redefines_base(self, robot: URRobot) -> None:
        robot.set_payload(2.0, [0.0, 0.0, 0.1])
        assert robot.base_payload == pytest.approx(2.0)
        robot.set_held_payload(0.1)
        robot.set_held_payload(0)
        mass, cog, _inertia = robot._rtde_c.setTargetPayload.call_args[0]
        assert mass == pytest.approx(2.0)
        assert cog == [0.0, 0.0, 0.1]


class TestPhysicalOverrides:
    def test_pops_and_applies(self) -> None:
        kwargs: dict[str, object] = {
            "mass": 0.8,
            "center_of_gravity": [0.0, 0.0, 0.06],
            "tcp_offset": [0.0, 0.0, 0.15, 0.0, 0.0, 0.0],
            "max_vacuum": 70,
        }
        mass, cog, tcp = _apply_physical_overrides(
            ROBOTIQ_EPICK_SINGLE_S,
            kwargs,
            (ROBOTIQ_EPICK_SINGLE_S.mass,
             list(ROBOTIQ_EPICK_SINGLE_S.center_of_gravity),
             list(ROBOTIQ_EPICK_SINGLE_S.tcp_offset)),
        )
        assert mass == 0.8
        assert cog == [0.0, 0.0, 0.06]
        assert tcp == [0.0, 0.0, 0.15, 0.0, 0.0, 0.0]
        # Only backend kwargs remain for the gripper constructor.
        assert kwargs == {"max_vacuum": 70}

    def test_no_overrides_unchanged(self) -> None:
        kwargs: dict[str, object] = {"max_vacuum": 70}
        mass, cog, tcp = _apply_physical_overrides(
            ROBOTIQ_EPICK_SINGLE_S,
            kwargs,
            (ROBOTIQ_EPICK_SINGLE_S.mass,
             list(ROBOTIQ_EPICK_SINGLE_S.center_of_gravity),
             list(ROBOTIQ_EPICK_SINGLE_S.tcp_offset)),
        )
        assert mass == ROBOTIQ_EPICK_SINGLE_S.mass
        assert cog == list(ROBOTIQ_EPICK_SINGLE_S.center_of_gravity)
        assert tcp == list(ROBOTIQ_EPICK_SINGLE_S.tcp_offset)
        assert kwargs == {"max_vacuum": 70}

    def test_non_preset_gripper_left_alone(self) -> None:
        # DigitalGripperConfig has no physical specs: keys stay in
        # kwargs and the backend's strict validation rejects them.
        kwargs: dict[str, object] = {"mass": 1.0}
        mass, cog, tcp = _apply_physical_overrides(
            DigitalGripperConfig(pin=3), kwargs, (0.0, [0.0, 0.0, 0.0], None)
        )
        assert mass == 0.0
        assert cog == [0.0, 0.0, 0.0]
        assert tcp is None
        assert kwargs == {"mass": 1.0}

    def test_none_gripper_left_alone(self) -> None:
        kwargs: dict[str, object] = {"mass": 1.0}
        mass, cog, tcp = _apply_physical_overrides(
            None, kwargs, (0.0, [0.0, 0.0, 0.0], None)
        )
        assert mass == 0.0
        assert kwargs == {"mass": 1.0}
