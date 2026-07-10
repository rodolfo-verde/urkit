"""URKit — Universal Robots e-Series control toolkit.

A high-level Python package for Universal Robots e-Series (UR5e, UR10e,
UR16e) built on ``ur_rtde``. Provides connection validation, named point
management, motion commands, gripper abstraction, telemetry, geometry
helpers, and an interactive teach pendant CLI.

Quick start::

    from urkit import URRobot, ROBOTIQ_HAND_E

    robot = URRobot(
        ip="192.168.1.50",
        points="points.db",
        gripper=ROBOTIQ_HAND_E,
    )

    robot.gripper.activate()
    robot.move_to("pick")
    robot.gripper.open()
    robot.move_to("place")
    robot.gripper.close()
"""

from __future__ import annotations

__version__ = "0.3.12"

from urkit.config import load_config, resolve_config
from urkit.exceptions import (
    URKitError,
    URKitConnectionError,
    MotionError,
    GripperError,
    PointError,
    URKitIOError,
    TelemetryError,
    URKitRuntimeError,
    RobotNotInRemoteModeError,
    RtdeRegisterConflictError,
)
from urkit.geometry import (
    MoveFrame,
    orient_tcp_down,
    quat_to_rotvec,
    quat_to_rpy,
    rpy_to_quat,
    rotvec_to_quat,
)
from urkit.gripper import Gripper
from urkit.gripper.presets import (
    DigitalGripperConfig,
    GripperPreset,
    PRESETS,
    ROBOTIQ_2F_85,
    ROBOTIQ_2F_140,
    ROBOTIQ_HAND_E,
)
from urkit.motion import FreedriveMode
from urkit.robot import URRobot

__all__ = [
    # Version
    "__version__",
    # Config
    "load_config",
    "resolve_config",
    # Core class
    "URRobot",
    # Gripper
    "Gripper",
    "GripperPreset",
    "DigitalGripperConfig",
    "PRESETS",
    "ROBOTIQ_2F_85",
    "ROBOTIQ_2F_140",
    "ROBOTIQ_HAND_E",
    # Freedrive mode
    "FreedriveMode",
    # Move frame
    "MoveFrame",
    # Geometry
    "orient_tcp_down",
    "quat_to_rotvec",
    "quat_to_rpy",
    "rpy_to_quat",
    "rotvec_to_quat",
    # Exceptions
    "URKitError",
    "URKitConnectionError",
    "MotionError",
    "GripperError",
    "PointError",
    "URKitIOError",
    "TelemetryError",
    "URKitRuntimeError",
    "RobotNotInRemoteModeError",
    "RtdeRegisterConflictError",
]
