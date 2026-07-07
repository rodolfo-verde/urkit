"""Digital I/O gripper backend.

Uses RTDE IO interface to control a simple on/off gripper via
a digital output pin.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from urkit.exceptions import GripperError
from urkit.gripper.base import Gripper

if TYPE_CHECKING:
    from rtde_control import RTDEControlInterface
    from rtde_receive import RTDEReceiveInterface

logger = logging.getLogger(__name__)


class DigitalGripper(Gripper):
    """Simple digital I/O gripper backend.

    Controls a gripper by setting/clearing a single digital output pin.
    Supports both normally-open and normally-closed grippers via the
    ``closed_when_high`` parameter.

    Args:
        rtde_control: RTDEControlInterface instance.
        rtde_receive: RTDEReceiveInterface instance (for feedback).
        pin: Digital output pin index (0–7 on e-Series).
        closed_when_high: If True, HIGH signal closes the gripper
                           (e.g., suction cup). If False, LOW closes it
                           (e.g., normally-closed solenoid gripper).
                           Default True.

    Example:
        >>> # Suction cup: HIGH = grab, LOW = release
        >>> gripper = DigitalGripper(rtde_c, rtde_r, pin=0)
        >>> # Normally-closed solenoid: LOW = grab, HIGH = release
        >>> gripper = DigitalGripper(rtde_c, rtde_r, pin=0, closed_when_high=False)
        >>> gripper.open()
        >>> gripper.close()
    """

    def __init__(
        self,
        rtde_control: "RTDEControlInterface",
        rtde_receive: "RTDEReceiveInterface",
        pin: int = 0,
        closed_when_high: bool = True,
        **kwargs: object,  # robot_ip passed by factory but not used
    ) -> None:
        self._rtde_c = rtde_control
        self._rtde_r = rtde_receive
        self._pin = pin
        self._closed_when_high = closed_when_high

        if not 0 <= pin <= 7:
            raise GripperError(
                f"Digital gripper pin must be 0–7, got {pin}. "
                "e-Series has 8 digital outputs (0–7)."
            )

        logger.info(
            "Digital gripper initialized on pin %d (closed_when_high=%s)",
            pin,
            closed_when_high,
        )

    def activate(self) -> None:
        """Activate the gripper.

        Raises:
            GripperError: Always — digital grippers don't require activation.
        """
        raise GripperError(
            "Digital grippers do not require activation. "
            "Remove the call to gripper.activate()."
        )

    def open(self) -> None:
        """Open the gripper (release)."""
        self._rtde_c.setStandardDigitalOut(self._pin, not self._closed_when_high)
        logger.debug(
            "Digital gripper opened (pin %d = %s)",
            self._pin,
            "OFF" if not self._closed_when_high else "ON",
        )

    def close(self) -> None:
        """Close the gripper (grab)."""
        self._rtde_c.setStandardDigitalOut(self._pin, self._closed_when_high)
        logger.debug(
            "Digital gripper closed (pin %d = %s)",
            self._pin,
            "ON" if self._closed_when_high else "OFF",
        )

    def set_position_mm(self, mm: float) -> None:
        """Set the gripper position.

        Raises:
            GripperError: Always — digital grippers don't support position control.
        """
        raise GripperError(
            "Digital grippers do not support set_position_mm. "
            "Use open() or close() instead."
        )

    def set_position_percent(self, percent: int, *, wait: bool = True) -> None:
        """Set the gripper position as a percentage.

        Raises:
            GripperError: Always — digital grippers don't support position control.
        """
        raise GripperError(
            "Digital grippers do not support set_position_percent. "
            "Use open() or close() instead."
        )

    def set_force(self, force: int) -> None:
        """Set gripper force.

        Raises:
            GripperError: Always — digital grippers don't support force control.
        """
        raise GripperError(
            "Digital grippers do not support set_force."
        )

    def set_speed(self, speed: int) -> None:
        """Set gripper speed.

        Raises:
            GripperError: Always — digital grippers don't support speed control.
        """
        raise GripperError(
            "Digital grippers do not support set_speed."
        )
