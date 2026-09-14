"""Tests for the Gripper factory method."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from urkit.exceptions import GripperError
from urkit.gripper import DigitalGripper, EpickGripper, RobotiqGripper
from urkit.gripper.base import Gripper
from urkit.gripper.epick import TAIL_SLEEP_S


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

    def test_create_epick(self):
        mock_rtde_c = MagicMock()
        mock_rtde_r = MagicMock()
        g = Gripper.create("epick", rtde_control=mock_rtde_c, rtde_receive=mock_rtde_r)
        assert isinstance(g, EpickGripper)
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

    def test_init_speed_out_of_range_raises(self):
        with pytest.raises(GripperError, match=r"0[–-]100"):
            RobotiqGripper(rtde_control=MagicMock(), speed=500)

    def test_rejects_epick_params(self):
        for kw in ({"max_vacuum": 70}, {"min_vacuum": 50}, {"grip_timeout": 40}):
            with pytest.raises(GripperError, match="EPick vacuum-gripper"):
                RobotiqGripper(rtde_control=MagicMock(), **kw)

    def test_rejects_unknown_param(self):
        with pytest.raises(GripperError, match="Unknown 2F gripper parameter"):
            RobotiqGripper(rtde_control=MagicMock(), max_travel=5)

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
        # activate (check+activate only) + open = 2 calls
        assert len(calls) == 2
        # Check the activate call contains activation logic
        activate_code = calls[0][0][1]
        assert "rq_is_gripper_activated()" in activate_code
        assert "rq_activate_and_wait()" in activate_code
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

    def test_rejects_robotiq_params(self):
        mock_rtde_c = MagicMock()
        mock_rtde_r = MagicMock()
        for kw in ({"force": 50}, {"speed": 50}, {"max_vacuum": 70}):
            with pytest.raises(GripperError, match="Robotiq gripper parameters"):
                DigitalGripper(mock_rtde_c, mock_rtde_r, pin=1, **kw)

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


class TestEpickGripper:
    """EpickGripper vacuum gripper backend tests."""

    def _gripper(self, **kwargs):
        mock_rtde = MagicMock()
        mock_rtde.sendCustomScriptFunction.return_value = True
        return EpickGripper(rtde_control=mock_rtde, **kwargs)

    def test_init_validates_rtde(self):
        with pytest.raises(GripperError, match="rtde_control"):
            EpickGripper(rtde_control=None)

    def test_init_defaults(self):
        g = self._gripper()
        assert g.is_activated() is False
        assert g.get_position_mm() is None
        assert g.max_travel_mm() is None

    def test_init_max_vacuum_range(self):
        for bad in (0, 10, 19, 101, 150):
            with pytest.raises(GripperError, match="max vacuum must be 20-100"):
                self._gripper(max_vacuum=bad, min_vacuum=10)
        for good in (20, 60, 100):
            assert self._gripper(max_vacuum=good, min_vacuum=10)._max_vacuum == good

    def test_init_min_vacuum_range(self):
        for bad in (0, 9):
            with pytest.raises(GripperError, match="min vacuum must be 10-60"):
                self._gripper(min_vacuum=bad)
        # Min above max is rejected at construction.
        with pytest.raises(GripperError, match="min vacuum must be 10-30"):
            self._gripper(max_vacuum=30, min_vacuum=40)
        assert self._gripper(max_vacuum=60, min_vacuum=50)._min_vacuum == 50

    def test_init_grip_timeout_range(self):
        for bad in (-1, 101):
            with pytest.raises(GripperError, match="grip timeout must be 0-100"):
                self._gripper(grip_timeout=bad)
        assert self._gripper(grip_timeout=30)._timeout_ms == 3000

    def test_rejects_2f_params(self):
        for kw in ({"force": 70}, {"speed": 50}, {"force": 70, "speed": 50}):
            with pytest.raises(GripperError, match="2F finger-gripper"):
                self._gripper(**kw)

    def test_rejects_unknown_param(self):
        with pytest.raises(GripperError, match="Unknown EPick gripper parameter"):
            self._gripper(pin=3)

    def test_set_max_vacuum_range(self):
        g = self._gripper()
        with pytest.raises(GripperError, match="max vacuum must be 20-100"):
            g.set_max_vacuum(19)
        g.set_max_vacuum(80)
        assert g._max_vacuum == 80

    def test_set_max_vacuum_below_min_raises(self):
        g = self._gripper()  # min vacuum 40
        with pytest.raises(GripperError, match="exceeds the new max vacuum"):
            g.set_max_vacuum(30)

    def test_set_min_vacuum_range(self):
        g = self._gripper()  # max vacuum 60
        with pytest.raises(GripperError, match="min vacuum must be 10-100"):
            g.set_min_vacuum(9)
        with pytest.raises(GripperError, match="min vacuum must be 10-100"):
            g.set_min_vacuum(101)
        g.set_min_vacuum(40)
        assert g._min_vacuum == 40

    def test_set_min_vacuum_above_max_raises(self):
        g = self._gripper(max_vacuum=50)  # min vacuum 40
        with pytest.raises(GripperError, match="exceeds max vacuum"):
            g.set_min_vacuum(60)

    def test_set_position_mm_raises(self):
        g = self._gripper()
        with pytest.raises(GripperError, match="no finger travel"):
            g.set_position_mm(10.0)

    def test_set_position_percent_range(self):
        g = self._gripper()
        with pytest.raises(GripperError, match="vacuum level must be 0-100"):
            g.set_position_percent(101)

    def test_close_requires_activation(self):
        g = self._gripper()
        with pytest.raises(GripperError, match="not activated"):
            g.close()

    def test_grip_script_uses_advanced_mode_and_obj_min(self):
        g = self._gripper(max_vacuum=60)
        script = g._grip_script(60, wait=True)
        # Advanced mode (rMOD=1) - auto mode false-positives in the air.
        assert 'rq_set_gripper_mode(1, "1")' in script
        # Success = OBJ==1 (secured to min) hit count, not OBJ 1/2.
        assert "epick_obj_min" in script
        assert "epick_hits" in script
        # POS = 100 - max_vacuum, FOR = 100 - min_vacuum (URCap mapping).
        assert "epick_set_params(40, 30, 60, \"1\")" in script
        # No break (not used in the verified preamble), tail sleep present.
        assert "break" not in script
        assert f"sleep({TAIL_SLEEP_S})" in script

    def test_release_script_uses_blow_off(self):
        g = self._gripper()
        script = g._release_script(wait=True)
        assert 'epick_set_params(255, 255, 0, "1")' in script
        assert 'rq_set_gripper_mode(1, "1")' in script
