"""Tests for GripperPreset and DigitalGripperConfig dataclasses."""

from __future__ import annotations

import os

import pytest

from urkit.gripper.presets import (
    GripperPreset,
    DigitalGripperConfig,
    PRESETS,
    ROBOTIQ_2F_85,
    ROBOTIQ_2F_140,
    ROBOTIQ_HAND_E,
)


def _robot_ip() -> str | None:
    """Get robot IP from environment or config."""
    ip = os.environ.get("ROBOT_IP")
    if ip:
        return ip
    try:
        from urkit.cli.teach import _load_config

        cfg = _load_config()
        return cfg.get("robot_ip")
    except Exception:
        return None


class TestGripperPresetDataclass:
    """Test GripperPreset dataclass properties."""

    def test_preset_is_frozen(self):
        preset = GripperPreset(
            "test", 1.0, [0, 0, 0.1], [0, 0, 0.1, 0, 0, 0], "robotiq",
        )
        with pytest.raises(Exception):
            preset.mass = 2.0  # type: ignore

    def test_preset_values(self):
        assert ROBOTIQ_2F_85.name == "2F-85"
        assert ROBOTIQ_2F_85.mass == 0.921
        assert ROBOTIQ_2F_85.center_of_gravity == [0.0, 0.0, 0.060]
        assert ROBOTIQ_2F_85.tcp_offset == [0.0, 0.0, 0.174, 0.0, 0.0, 0.0]
        assert ROBOTIQ_2F_85.backend == "robotiq"
        assert ROBOTIQ_2F_85.force == 100
        assert ROBOTIQ_2F_85.speed == 100

    def test_all_presets_in_registry(self):
        assert "2F-85" in PRESETS
        assert "2F-140" in PRESETS
        assert "HAND-E" in PRESETS
        assert PRESETS["2F-85"] is ROBOTIQ_2F_85
        assert PRESETS["2F-140"] is ROBOTIQ_2F_140
        assert PRESETS["HAND-E"] is ROBOTIQ_HAND_E

    def test_2f_140_values(self):
        assert ROBOTIQ_2F_140.name == "2F-140"
        assert ROBOTIQ_2F_140.mass == 1.013
        assert ROBOTIQ_2F_140.tcp_offset == [0.0, 0.0, 0.244, 0.0, 0.0, 0.0]

    def test_hand_e_values(self):
        assert ROBOTIQ_HAND_E.name == "Hand-E"
        assert ROBOTIQ_HAND_E.mass == 1.068
        assert ROBOTIQ_HAND_E.tcp_offset == [0.0, 0.0, 0.157, 0.0, 0.0, 0.0]


class TestDigitalGripperConfig:
    """Test DigitalGripperConfig dataclass."""

    def test_default_config(self):
        config = DigitalGripperConfig(pin=3)
        assert config.pin == 3
        assert config.close_on_high is True

    def test_custom_config(self):
        config = DigitalGripperConfig(pin=5, close_on_high=False)
        assert config.pin == 5
        assert config.close_on_high is False


class TestURRobotPresetIntegration:
    """Test URRobot constructor resolves presets correctly against a real robot.

    Requires ROBOT_IP environment variable or config robot_ip.
    """

    @pytest.mark.parametrize(
        "gripper,payload",
        [
            (ROBOTIQ_2F_85, 0.921),
            (ROBOTIQ_HAND_E, 1.068),
        ],
    )
    def test_preset_sets_payload(self, gripper, payload):
        """Preset should set payload correctly."""
        ip = _robot_ip()
        if not ip:
            pytest.skip("ROBOT_IP not set")
        try:
            from urkit.robot import URRobot

            r = URRobot(ip=ip, auto_start=True, gripper=gripper)
        except Exception as e:
            pytest.skip(f"Failed to connect: {e}")
        try:
            actual = r.get_payload()
            assert actual == pytest.approx(payload, rel=0.01)
        finally:
            r.disconnect()

    def test_preset_creates_gripper(self):
        """Preset should create a robotiq gripper."""
        ip = _robot_ip()
        if not ip:
            pytest.skip("ROBOT_IP not set")
        try:
            from urkit.robot import URRobot

            r = URRobot(ip=ip, auto_start=True, gripper=ROBOTIQ_2F_85)
        except Exception as e:
            pytest.skip(f"Failed to connect: {e}")
        try:
            assert r.gripper is not None
            from urkit.gripper.robotiq import RobotiqGripper

            assert isinstance(r.gripper, RobotiqGripper)
        finally:
            r.disconnect()

    def test_preset_does_not_mutate_original(self):
        """URRobot should not mutate the preset's lists."""
        preset = GripperPreset(
            "test", 1.0, [0, 0, 0.1], [0, 0, 0.1, 0, 0, 0], "robotiq",
        )
        original_cog = list(preset.center_of_gravity)
        original_tcp = list(preset.tcp_offset)
        ip = _robot_ip()
        if not ip:
            pytest.skip("ROBOT_IP not set")
        try:
            from urkit.robot import URRobot

            r = URRobot(ip=ip, auto_start=True, gripper=preset)
            r.disconnect()
        except Exception:
            pytest.skip("Failed to connect")
        assert preset.center_of_gravity == original_cog
        assert preset.tcp_offset == original_tcp
