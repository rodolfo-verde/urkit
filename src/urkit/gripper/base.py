"""Abstract gripper plugin interface.

All gripper backends must implement this interface so that
``robot.gripper.open()``, ``close()``, ``set_position_mm()``, and ``set_position_percent()`` work
uniformly regardless of the underlying hardware.
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class Gripper(ABC):
    """Abstract base class for gripper backends.

    Subclasses must implement ``open()``, ``close()``, ``set_position_mm()``, and ``set_position_percent()``.
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
    def set_position_mm(self, mm: float) -> None:
        """Set the gripper to a specific position in millimeters.

        For Robotiq 2F grippers, mm is 0 (fully closed) to max_mm
        (fully open). Digital grippers don't support this and raise
        GripperError.

        Args:
            mm: Opening in millimeters.

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
        to re-enable.
        """

    def disconnect(self) -> None:
        """Disconnect the gripper.

        No-op by default. Override in subclasses that need to close
        sockets or release resources (e.g., Robotiq grippers).
        """

    def set_position_percent(self, percent: int, *, wait: bool = True) -> None:
        """Set the gripper to a specific percentage opening.

        0 = fully open, 100 = fully closed.

        Args:
            percent: Percentage opening (0-100).
            wait: If True, block until the gripper reaches the target
                position (default True).

        Raises:
            GripperError: If percent is out of range or the operation
                fails.
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
    def create(cls, name: str, **kwargs: object) -> "Gripper":
        """Factory method to create a gripper backend."""
        from urkit.gripper.robotiq import RobotiqGripper
        from urkit.gripper.digital import DigitalGripper

        if name == "robotiq":
            return RobotiqGripper(**kwargs)  # type: ignore[arg-type]
        elif name == "digital":
            return DigitalGripper(**kwargs)  # type: ignore[arg-type]
        else:
            from urkit.exceptions import GripperError

            raise GripperError(
                f"Unknown gripper backend: '{name}'. "
                f"Supported backends: robotiq, digital."
            )
