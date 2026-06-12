"""URKit exception hierarchy.

All urkit errors derive from URKitError. Subclasses provide
descriptive, actionable messages for failure modes.
"""

from __future__ import annotations


class URKitError(Exception):
    """Base exception for all URKit errors."""


class URKitConnectionError(URKitError):
    """Raised when robot connection or pre-connection validation fails.

    Covers ping failures, port checks, remote mode checks, and RTDE
    connection drops.
    """


class MotionError(URKitError):
    """Raised when a motion command fails."""


class GripperError(URKitError):
    """Raised when a gripper operation fails."""


class PointError(URKitError):
    """Raised when point file operations fail (corrupt file, not found, etc.)."""


class URKitIOError(URKitError):
    """Raised when a digital I/O operation fails."""


class TelemetryError(URKitError):
    """Raised when telemetry data cannot be read."""


class URKitRuntimeError(URKitError):
    """Raised when the robot is in an invalid state during runtime."""


class RobotNotInRemoteModeError(URKitError):
    """Raised when RTDE connection fails because the robot is not in remote mode."""


class RtdeRegisterConflictError(URKitError):
    """Raised when RTDE registers are already claimed by another protocol."""
