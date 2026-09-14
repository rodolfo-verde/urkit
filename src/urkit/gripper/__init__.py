"""Gripper plugin package.

Exports the Gripper base class, factory, and configuration presets.

Usage::

    from urkit import URRobot, ROBOTIQ_2F_85, DigitalGripperConfig

    # Robotiq preset — one arg does everything
    robot = URRobot(ip="192.168.1.50", gripper=ROBOTIQ_2F_85)

    # Digital I/O gripper
    robot = URRobot(ip="192.168.1.50", gripper=DigitalGripperConfig(pin=3))
"""

from urkit.gripper.base import Gripper
from urkit.gripper.digital import DigitalGripper
from urkit.gripper.epick import EpickGripper
from urkit.gripper.robotiq import RobotiqGripper
from urkit.gripper.presets import (
    DigitalGripperConfig,
    GripperPreset,
    ROBOTIQ_2F_85,
    ROBOTIQ_2F_140,
    ROBOTIQ_EPICK_DUAL_L,
    ROBOTIQ_EPICK_DUAL_S,
    ROBOTIQ_EPICK_QUAD_L,
    ROBOTIQ_EPICK_QUAD_S,
    ROBOTIQ_EPICK_SINGLE_L,
    ROBOTIQ_EPICK_SINGLE_S,
    ROBOTIQ_HAND_E,
)

__all__ = [
    "Gripper",
    "RobotiqGripper",
    "EpickGripper",
    "DigitalGripper",
    "GripperPreset",
    "DigitalGripperConfig",
    "ROBOTIQ_2F_85",
    "ROBOTIQ_2F_140",
    "ROBOTIQ_HAND_E",
    "ROBOTIQ_EPICK_SINGLE_S",
    "ROBOTIQ_EPICK_SINGLE_L",
    "ROBOTIQ_EPICK_DUAL_S",
    "ROBOTIQ_EPICK_DUAL_L",
    "ROBOTIQ_EPICK_QUAD_S",
    "ROBOTIQ_EPICK_QUAD_L",
]
