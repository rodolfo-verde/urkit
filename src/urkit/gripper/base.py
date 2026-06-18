"""Abstract gripper plugin interface.

All gripper backends must implement this interface so that
``robot.gripper.open()``, ``close()``, and ``set_position()`` work
uniformly regardless of the underlying hardware.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Gripper(ABC):
    """Abstract base class for gripper backends.

    Subclasses must implement ``open()``, ``close()``, and ``set_position()``.
    The ``activate()`` method is a no-op by default and should be overridden
    by backends that require explicit activation (e.g., Robotiq). The factory
    method ``Gripper.create()`` returns the appropriate backend.
    """

    @abstractmethod
    def open(self) -> None:
        """Open the gripper (release).

        Raises:
            GripperError: If the operation fails.
        """

    @abstractmethod
    def close(self) -> None:
        """Close the gripper (grip).

        Raises:
            GripperError: If the operation fails.
        """

    @abstractmethod
    def set_position(self, position: int) -> None:
        """Set the gripper to a specific position.

        For Robotiq 2F grippers, position is 0-100 (0 = fully open,
        100 = fully closed). Digital grippers don't support this and
        raise GripperError.

        Args:
            position: Gripper position.

        Raises:
            GripperError: If the operation fails.
        """

    def activate(self) -> None:
        """Activate the gripper.

        No-op by default. Override in subclasses that require explicit
        activation (e.g., Robotiq grippers need a reset and calibration
        sequence). DigitalGripper raises GripperError to signal that
        activation is not needed.

        Raises:
            GripperError: If activation fails or is not applicable.
        """

    def deactivate(self) -> None:
        """Deactivate the gripper.

        No-op by default. Override in subclasses that support explicit
        deactivation (e.g., Robotiq grippers). Call activate() again
        to re-enable the gripper.
        """

    def get_position_mm(self) -> float | None:
        """Return the last commanded position in mm, or None if unknown.

        Returns the most recently set position. Subclasses that support
        reading the actual hardware position should override this method.

        Returns:
            Position in mm, or None if not available.
        """
        return None

    def max_travel_mm(self) -> float | None:
        """Return the maximum finger travel in mm, or None if unknown.

        Returns:
            Max travel in mm, or None.
        """
        return None

    @classmethod
    def create(cls, name: str, **kwargs) -> "Gripper":
        """Factory method to create a gripper backend.

        Args:
            name: Backend name. Supported values:
                  - ``"robotiq"`` — Robotiq 2F via URScript (secondary interface)
                  - ``"digital"`` — Digital I/O gripper

        Kwargs:
            rtde_control: RTDEControlInterface (required for all backends).
            pin: Digital output pin index (required for "digital" backend).
            force: Gripper force 0–100 (Robotiq backend, default 100).
            speed: Gripper speed 0–100 (Robotiq backend, default 100).

        Returns:
            A concrete Gripper instance.

        Raises:
            GripperError: If the backend name is unknown.
        """
        from urkit.gripper.robotiq import RobotiqGripper
        from urkit.gripper.digital import DigitalGripper

        if name == "robotiq":
            return RobotiqGripper(**kwargs)
        elif name == "digital":
            return DigitalGripper(**kwargs)
        else:
            from urkit.exceptions import GripperError

            raise GripperError(
                f"Unknown gripper backend: '{name}'. "
                f"Supported backends: robotiq, digital."
            )
