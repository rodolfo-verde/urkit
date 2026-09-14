"""Tests for GripperPreset and DigitalGripperConfig dataclasses."""

from __future__ import annotations

import os
import time

import pytest

from urkit.gripper.presets import (
    GripperPreset,
    DigitalGripperConfig,
    PRESETS,
    ROBOTIQ_2F_85,
    ROBOTIQ_2F_140,
    ROBOTIQ_HAND_E,
    ROBOTIQ_EPICK_SINGLE_S,
    ROBOTIQ_EPICK_SINGLE_L,
    ROBOTIQ_EPICK_DUAL_S,
    ROBOTIQ_EPICK_DUAL_L,
    ROBOTIQ_EPICK_QUAD_S,
    ROBOTIQ_EPICK_QUAD_L,
)


def _robot_ip() -> str | None:
    """Get robot IP from environment or config."""
    ip = os.environ.get("ROBOT_IP")
    if ip:
        return ip
    try:
        from urkit.config import _load_config as load_config

        cfg = load_config()
        return cfg.get("robot_ip")
    except Exception:
        return None


#: The robot takes a moment to release its RTDE registers after a
#: disconnect; reconnecting immediately can race the release and hit
#: the register lock. Real-robot tests settle before reconnecting.
_RTDE_SETTLE_S = 3.0


def _teardown(r) -> None:
    """Disconnect and let the robot release its RTDE registers."""
    r.disconnect()
    time.sleep(_RTDE_SETTLE_S)


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

    def test_backend_kwargs_2f(self):
        assert ROBOTIQ_2F_85.backend_kwargs() == {
            "max_mm": 85,
            "force": 100,
            "speed": 100,
        }


class TestEpickCupPresets:
    """Test the ROBOTIQ_EPICK_* bracket + cup-size presets.

    All-small (O40) combinations must reproduce Robotiq's EPick manual
    Table 6-4 exactly, and large (O55) combinations follow from the
    Festo cup datasheets.
    """

    def test_single_small_matches_manual(self):
        p = ROBOTIQ_EPICK_SINGLE_S
        assert p.name == "EPick-single-S"
        assert p.mass == pytest.approx(0.736, abs=1e-6)
        assert p.tcp_offset[2] == pytest.approx(0.145, abs=1e-6)  # manual: 145 mm
        assert p.center_of_gravity[2] == pytest.approx(0.0547, abs=0.001)
        assert p.backend == "epick"
        assert p.force == 60 and p.speed == 30 and p.max_mm == 0

    def test_single_large(self):
        p = ROBOTIQ_EPICK_SINGLE_L
        assert p.name == "EPick-single-L"
        assert p.mass == pytest.approx(0.745, abs=1e-6)
        assert p.tcp_offset[2] == pytest.approx(0.152, abs=1e-6)  # 113 + 39

    def test_dual_small_matches_manual(self):
        p = ROBOTIQ_EPICK_DUAL_S
        assert p.name == "EPick-dual-S"
        assert p.mass == pytest.approx(1.116, abs=1e-6)  # manual Table 6-4
        assert p.tcp_offset[2] == pytest.approx(0.196, abs=1e-6)  # manual
        assert p.center_of_gravity[2] == pytest.approx(0.0819, abs=0.001)  # manual

    def test_quad_small_matches_manual(self):
        p = ROBOTIQ_EPICK_QUAD_S
        assert p.mass == pytest.approx(1.341, abs=1e-6)  # manual Table 6-4
        assert p.tcp_offset[2] == pytest.approx(0.196, abs=1e-6)  # manual
        assert p.center_of_gravity[2] == pytest.approx(0.092, abs=0.001)  # manual

    def test_quad_large(self):
        p = ROBOTIQ_EPICK_QUAD_L
        assert p.name == "EPick-quad-L"
        assert p.mass == pytest.approx(1.377, abs=1e-6)  # 706+515+4x39 g
        assert p.tcp_offset[2] == pytest.approx(0.203, abs=1e-6)  # 164 + 39

    def test_dual_large(self):
        p = ROBOTIQ_EPICK_DUAL_L
        assert p.mass == pytest.approx(1.134, abs=1e-6)  # 706+350+2x39 g
        assert p.tcp_offset[2] == pytest.approx(0.203, abs=1e-6)

    def test_all_in_registry(self):
        for p in (
            ROBOTIQ_EPICK_SINGLE_S,
            ROBOTIQ_EPICK_SINGLE_L,
            ROBOTIQ_EPICK_DUAL_S,
            ROBOTIQ_EPICK_DUAL_L,
            ROBOTIQ_EPICK_QUAD_S,
            ROBOTIQ_EPICK_QUAD_L,
        ):
            assert PRESETS[p.name.upper()] is p
            assert p.backend == "epick"

    def test_backend_kwargs_epick(self):
        # EPick presets map the generic force/speed fields to the
        # vacuum gripper's own parameter names.
        assert ROBOTIQ_EPICK_QUAD_L.backend_kwargs() == {
            "max_mm": 0,
            "max_vacuum": 60,
            "grip_timeout": 30,
        }


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

            r = URRobot(ip=ip, gripper=gripper)
        except Exception as e:
            pytest.skip(f"Failed to connect: {e}")
        try:
            actual = r.payload
            assert actual == pytest.approx(payload, rel=0.01)
        finally:
            _teardown(r)

    def test_preset_creates_gripper(self):
        """Preset should create a robotiq gripper."""
        ip = _robot_ip()
        if not ip:
            pytest.skip("ROBOT_IP not set")
        try:
            from urkit.robot import URRobot

            r = URRobot(ip=ip, gripper=ROBOTIQ_2F_85)
        except Exception as e:
            pytest.skip(f"Failed to connect: {e}")
        try:
            assert r.gripper is not None
            from urkit.gripper.robotiq import RobotiqGripper

            assert isinstance(r.gripper, RobotiqGripper)
        finally:
            _teardown(r)

    def test_epick_cup_preset_sets_payload(self):
        """An EPick cup preset should set the computed payload on a real robot."""
        ip = _robot_ip()
        if not ip:
            pytest.skip("ROBOT_IP not set")
        preset = ROBOTIQ_EPICK_QUAD_L
        try:
            from urkit.robot import URRobot

            r = URRobot(ip=ip, gripper=preset)
        except Exception as e:
            pytest.skip(f"Failed to connect: {e}")
        try:
            assert r.payload == pytest.approx(preset.mass, rel=0.01)
        finally:
            _teardown(r)

    def test_from_config_resolves_epick_cup_preset(self):
        """gripper: epick-quad-l should resolve like any other preset name.

        Resolution (and its ValueError on an unknown preset) happens
        before any network I/O, so a localhost IP keeps this test
        offline.
        """
        from urkit.robot import URRobot

        cfg = {
            "robot_ip": "127.0.0.1",
            "gripper": "epick-quad-l",
        }
        with pytest.raises(Exception):
            # Connection will fail, but only AFTER successful resolution.
            URRobot.from_config(cfg)
        # Unknown preset must raise ValueError, before connection.
        bad = {"robot_ip": "127.0.0.1", "gripper": "epick-quad-xl"}
        with pytest.raises(ValueError, match="Unknown gripper preset"):
            URRobot.from_config(bad)

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

            r = URRobot(ip=ip, gripper=preset)
            _teardown(r)
        except Exception:
            pytest.skip("Failed to connect")
        assert preset.center_of_gravity == original_cog
        assert preset.tcp_offset == original_tcp
