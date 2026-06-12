"""Tests for the URKit exception hierarchy."""

from __future__ import annotations

from urkit.exceptions import (
    URKitError,
    URKitConnectionError,
    MotionError,
    GripperError,
    PointError,
    URKitIOError,
    TelemetryError,
    URKitRuntimeError,
)


class TestExceptionInheritance:
    """All URKit exceptions should inherit from URKitError."""

    def test_connection_error_inherits_urkit_error(self):
        assert issubclass(URKitConnectionError, URKitError)

    def test_motion_error_inherits_urkit_error(self):
        assert issubclass(MotionError, URKitError)

    def test_gripper_error_inherits_urkit_error(self):
        assert issubclass(GripperError, URKitError)

    def test_point_error_inherits_urkit_error(self):
        assert issubclass(PointError, URKitError)

    def test_io_error_inherits_urkit_error(self):
        assert issubclass(URKitIOError, URKitError)

    def test_telemetry_error_inherits_urkit_error(self):
        assert issubclass(TelemetryError, URKitError)

    def test_runtime_error_inherits_urkit_error(self):
        assert issubclass(URKitRuntimeError, URKitError)

    def test_all_inherit_from_base_exception(self):
        """URKitError itself inherits from Exception."""
        assert issubclass(URKitError, Exception)


class TestRaiseAndCatch:
    """Each exception can be raised and caught as URKitError."""

    def _raise_and_catch(self, exc_class):
        try:
            raise exc_class("test message")
        except URKitError as e:
            assert str(e) == "test message"
            return True
        assert False, f"Failed to catch {exc_class.__name__} as URKitError"

    def test_catch_connection_error(self):
        assert self._raise_and_catch(URKitConnectionError)

    def test_catch_motion_error(self):
        assert self._raise_and_catch(MotionError)

    def test_catch_gripper_error(self):
        assert self._raise_and_catch(GripperError)

    def test_catch_point_error(self):
        assert self._raise_and_catch(PointError)

    def test_catch_io_error(self):
        assert self._raise_and_catch(URKitIOError)

    def test_catch_telemetry_error(self):
        assert self._raise_and_catch(TelemetryError)

    def test_catch_runtime_error(self):
        assert self._raise_and_catch(URKitRuntimeError)


class TestURKitErrorNotBuiltin:
    """URKit names must not shadow Python builtins."""

    def test_connection_error_not_builtin(self):
        import builtins
        assert URKitConnectionError is not builtins.ConnectionError

    def test_io_error_not_builtin(self):
        import builtins
        assert URKitIOError is not builtins.IOError

    def test_runtime_error_not_builtin(self):
        import builtins
        assert URKitRuntimeError is not builtins.RuntimeError
