"""Tests for the F-key freedrive cycle (_next_freedrive_step).

The cycle must be OFF -> ALL -> XYZ -> OFF (custom axes set via the
3-key submenu cycle to OFF on the next press). Before the fix, F only
toggled ALL <-> XYZ and could never turn freedrive off.
"""

from __future__ import annotations

import pytest

from urkit.cli.teach import _initial_freedrive_axes, _next_freedrive_step
from urkit.motion import FreedriveMode


def _state(freedrive: bool, mode=object, custom=object) -> dict:
    state: dict = {"freedrive": freedrive}
    if mode is not object:
        state["freedrive_mode"] = mode
    if custom is not object:
        state["_fd_custom_axes"] = custom
    return state


class TestOffToOn:
    def test_off_defaults_to_all(self):
        assert _next_freedrive_step(_state(False)) == (False, FreedriveMode.ALL)

    def test_off_resumes_last_custom_axes(self):
        custom = [1, 1, 0, 0, 0, 0]
        assert _next_freedrive_step(_state(False, custom=custom)) == (
            False,
            custom,
        )


class TestOnToNext:
    def test_all_goes_to_xyz(self):
        assert _next_freedrive_step(
            _state(True, FreedriveMode.ALL)
        ) == (False, FreedriveMode.XYZ)

    def test_xyz_goes_off(self):
        assert _next_freedrive_step(_state(True, FreedriveMode.XYZ)) == (
            True,
            None,
        )

    def test_rotation_goes_off(self):
        assert _next_freedrive_step(_state(True, FreedriveMode.ROTATION)) == (
            True,
            None,
        )

    def test_custom_axes_go_off(self):
        assert _next_freedrive_step(_state(True, [1, 1, 0, 0, 0, 0])) == (
            True,
            None,
        )


class TestInitialAxes:
    """The axis picker's starting state."""

    def test_off_starts_fully_locked(self):
        # Preselect flow: enable exactly what you want, no stale checks.
        assert _initial_freedrive_axes(_state(False, FreedriveMode.ALL)) == [
            0, 0, 0, 0, 0, 0,
        ]

    def test_off_ignores_previous_mode(self):
        # Even with a preselection saved from an earlier session state,
        # the picker opens locked.
        assert _initial_freedrive_axes(_state(False, [1, 0, 1, 0, 0, 0])) == [
            0, 0, 0, 0, 0, 0,
        ]

    def test_on_all(self):
        assert _initial_freedrive_axes(_state(True, FreedriveMode.ALL)) == [
            1, 1, 1, 1, 1, 1,
        ]

    def test_on_xyz(self):
        assert _initial_freedrive_axes(_state(True, FreedriveMode.XYZ)) == [
            1, 1, 1, 0, 0, 0,
        ]

    def test_on_rotation(self):
        assert _initial_freedrive_axes(_state(True, FreedriveMode.ROTATION)) == [
            0, 0, 0, 1, 1, 1,
        ]

    def test_on_custom_list(self):
        assert _initial_freedrive_axes(_state(True, [1, 0, 1, 0, 0, 0])) == [
            1, 0, 1, 0, 0, 0,
        ]
