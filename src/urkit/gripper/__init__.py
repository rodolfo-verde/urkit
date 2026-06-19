"""Gripper plugin package.

Exports the Gripper base class, factory, and configuration presets.

Usage::

    from urkit import URRobot, ROBOTIQ_2F_85, DigitalGripperConfig

    # Robotiq preset — one arg does everything
    robot = URRobot(ip="172.31.1.42", gripper=ROBOTIQ_2F_85)

    # Digital I/O gripper
    robot = URRobot(ip="172.31.1.42", gripper=DigitalGripperConfig(pin=3))
"""

from urkit.gripper.base import Gripper
from urkit.gripper.digital import DigitalGripper
from urkit.gripper.robotiq import RobotiqGripper
from urkit.gripper.presets import (
    DigitalGripperConfig,
    GripperPreset,
    ROBOTIQ_2F_85,
    ROBOTIQ_2F_140,
    ROBOTIQ_HAND_E,
)

__all__ = [
    "Gripper",
    "RobotiqGripper",
    "DigitalGripper",
    "GripperPreset",
    "DigitalGripperConfig",
    "ROBOTIQ_2F_85",
    "ROBOTIQ_2F_140",
    "ROBOTIQ_HAND_E",
]
