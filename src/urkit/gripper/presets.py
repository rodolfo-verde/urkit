"""Gripper presets and configuration dataclasses.

Built-in presets for common Robotiq grippers. Each preset carries the
mass, center of gravity, TCP offset, and backend type — everything
needed to configure the robot for that gripper in a single argument.

Usage::

    from urkit import URRobot
    from urkit.gripper.presets import ROBOTIQ_2F_85

    # One arg — specs + backend
    robot = URRobot(ip="172.31.1.42", gripper=ROBOTIQ_2F_85)

    # Digital I/O gripper
    from urkit.gripper.presets import DigitalGripperConfig

    robot = URRobot(ip="172.31.1.42", gripper=DigitalGripperConfig(pin=3))
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GripperPreset:
    """Gripper preset with physical specs and backend type.

    Args:
        name: Human-readable identifier (e.g. ``"2F-85"``).
        mass: Mass in kg.
        center_of_gravity: Center of gravity in tool coordinates [x, y, z], meters.
        tcp_offset: TCP offset [x, y, z, rx, ry, rz], meters/radians.
        backend: Gripper backend name (e.g. ``"robotiq"``).
        max_mm: Maximum finger travel in mm (for ``set_position()``).
        force: Gripper force 0-100 (default 100).
        speed: Gripper speed 0-100 (default 100).
    """

    name: str
    mass: float
    center_of_gravity: list[float]
    tcp_offset: list[float]
    backend: str
    max_mm: int = 50
    force: int = 100
    speed: int = 100


@dataclass(frozen=True)
class DigitalGripperConfig:
    """Configuration for a digital I/O gripper.

    Digital grippers have no standard physical specs — just a pin
    and polarity. Pass this instead of a ``GripperPreset`` when
    using a suction cup, solenoid gripper, or custom actuator.

    Args:
        pin: Digital output pin index (0-7).
        close_on_high: If True, HIGH signal closes the gripper
            (default True — suction cups, electromagnetic grippers).
            If False, LOW signal closes it (normally-closed solenoid).
    """

    pin: int
    close_on_high: bool = True


# ---------------------------------------------------------------------------
# Robotiq 2-Finger Adaptive Grippers
# ---------------------------------------------------------------------------

ROBOTIQ_2F_85 = GripperPreset(
    name="2F-85",
    mass=0.921,
    center_of_gravity=[0.0, 0.0, 0.060],
    tcp_offset=[0.0, 0.0, 0.174, 0.0, 0.0, 0.0],
    backend="robotiq",
    max_mm=85,
)

ROBOTIQ_2F_140 = GripperPreset(
    name="2F-140",
    mass=1.013,
    center_of_gravity=[0.0, 0.0, 0.0755],
    tcp_offset=[0.0, 0.0, 0.244, 0.0, 0.0, 0.0],
    backend="robotiq",
    max_mm=140,
)

# ---------------------------------------------------------------------------
# Robotiq 2F-140-E (Hand-E series)
# ---------------------------------------------------------------------------

ROBOTIQ_HAND_E = GripperPreset(
    name="Hand-E",
    mass=1.068,
    center_of_gravity=[0.0, 0.0, 0.059],
    tcp_offset=[0.0, 0.0, 0.157, 0.0, 0.0, 0.0],
    backend="robotiq",
    max_mm=50,
)

# ---------------------------------------------------------------------------
# Registry — all built-in presets
# ---------------------------------------------------------------------------

PRESETS: dict[str, GripperPreset] = {
    p.name.upper(): p
    for p in (ROBOTIQ_2F_85, ROBOTIQ_2F_140, ROBOTIQ_HAND_E)
}
"""Lookup dict keyed by uppercase preset name."""
