"""Gripper presets and configuration dataclasses.

Built-in presets for common Robotiq grippers. Each preset carries the
mass, center of gravity, TCP offset, and backend type — everything
needed to configure the robot for that gripper in a single argument.

Usage::

    from urkit import URRobot
    from urkit.gripper.presets import ROBOTIQ_2F_85

    # One arg — specs + backend
    robot = URRobot(ip="192.168.1.50", gripper=ROBOTIQ_2F_85)

    # Digital I/O gripper
    from urkit.gripper.presets import DigitalGripperConfig

    robot = URRobot(ip="192.168.1.50", gripper=DigitalGripperConfig(pin=3))
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
        max_mm: Maximum finger travel in mm (for ``set_position_mm()``).
        force: 2F: finger force 0-100. EPick: max vacuum level 20-100
            (default 100, 60 for the EPick presets).
        speed: 2F: finger speed 0-100. EPick: grip timeout 0-100 in
            100 ms units (default 100, 30 for the EPick presets).
    """

    name: str
    mass: float
    center_of_gravity: list[float]
    tcp_offset: list[float]
    backend: str
    max_mm: int = 50
    force: int = 100
    speed: int = 100

    def backend_kwargs(self) -> dict[str, int]:
        """Backend constructor kwargs for this preset.

        The ``force``/``speed`` fields carry backend-specific meaning
        (finger force/speed for the 2F, max vacuum level and grip
        timeout for the EPick). This translates them to the backend's
        own parameter names.
        """
        if self.backend == "epick":
            return {
                "max_mm": self.max_mm,
                "max_vacuum": self.force,
                "grip_timeout": self.speed,
            }
        return {
            "max_mm": self.max_mm,
            "force": self.force,
            "speed": self.speed,
        }


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
# Robotiq EPick (vacuum gripper)
# ---------------------------------------------------------------------------

# e-Series coupling (ISO 9409-1-50-4-M6). The standard kit ships two
# standard suction cups (Ø 40 mm and Ø 55 mm, 1.5 bellows). One preset
# per bracket system + cup size is built below by _epick_preset();
# configurations without cups cannot grip and have no preset (pass
# mass / center_of_gravity / tcp_offset overrides during setup). For
# the EPick, force = max vacuum level (Robotiq URCap default 60%) and
# speed = grip timeout (x100 ms); max_mm is not applicable. The
# gripper runs in advanced mode (rMOD=1) for constant, hold-verified
# grip behavior.

# Component model for building any EPick suction cup configuration.
# Sources:
#   Body and cup rows: Robotiq EPick manual Table 6-4 (2021).  The table
#   bundles cups with the bracket and its nominal cup is the O40: the
#   single-cup row is +35 g / +32 mm, which matches the O40 cup, and the
#   dual/quad rows share one bracket stack height.  Bracket stack mass
#   and CoG are derived by subtracting body and cup contributions from
#   the table rows.
#   Cup mass: official Festo datasheets for the cups Robotiq ships
#   (VASB-40-1/4-PUR-B = 30 g, VASB-55-1/4-PUR-B = 39 g; part numbers
#   from Robotiq's own support article on EPick/Airpick suction cups).
#   Cup height: O40 = 32 mm (Table 6-4 single-cup row, 145 - 113),
#   O55 = 39 mm (STEP CAD bounding box, which underestimates true
#   extrema by ~2-3 mm; the same CAD gives ~31 mm for the O40, matching
#   the table's 32 mm).
# All-O40 combinations therefore reproduce Table 6-4 exactly.  Bracket
# mass uncertainty is ~15 g, O55 height ~2 mm; for critical setups,
# measure the actual stack and pass mass / center_of_gravity /
# tcp_offset overrides instead.
EPICK_BODY_MASS_KG = 0.706
EPICK_BODY_COG_Z_MM = 51.5
EPICK_BODY_TCP_Z_MM = 113.0
# Cup size code: (mass kg, height m).  "s" = O40, "l" = O55.
EPICK_CUP_SPECS: dict[str, tuple[float, float]] = {
    "s": (0.030, 0.032),
    "l": (0.039, 0.039),
}
# System: (cup count, bracket mass kg, bracket CoG z m).
# The bracket stack (manifold + bracket + air nodes + plugs) spans
# 51 mm below the body in both the dual and quad systems.
EPICK_SYSTEM_SPECS: dict[str, tuple[int, float, float]] = {
    "single": (1, 0.0, 0.0),
    "dual": (2, 0.350, 126.4),
    "quad": (4, 0.515, 127.0),
}
EPICK_BRACKET_STACK_MM = 51.0


def _epick_preset(system: str, cup: str) -> GripperPreset:
    """Build an EPick preset for a bracket system + cup size.

    Computes mass, center of gravity, and TCP for the system with all
    cups of one size (the kits ship identical-size sets, and a bracket
    runs cups of a single size): the EPick body plus (for dual/quad)
    the bracket system plus the system's cups.  TCP z is the bottom of
    the cups, the limiting point for approach moves.  The six exported
    ROBOTIQ_EPICK_* constants below are built by this function.

    Args:
        system: ``"single"`` (one cup on the generator main port),
            ``"dual"`` (2-cup bracket), or ``"quad"`` (4-cup bracket).
        cup: Cup size code for all cups: ``"s"`` = O40 (small) or
            ``"l"`` = O55 (large).

    Returns:
        A :class:`GripperPreset` with the EPick gripper parameters
        (force 60 = max vacuum, speed 30 = 3 s grip timeout).

    Raises:
        ValueError: If the system or cup code is invalid.
    """
    key = system.strip().lower()
    if key not in EPICK_SYSTEM_SPECS:
        raise ValueError(
            f"Unknown EPick system: {system!r}. "
            f"Available: {', '.join(sorted(EPICK_SYSTEM_SPECS))}."
        )
    count, bracket_kg, bracket_cog_mm = EPICK_SYSTEM_SPECS[key]

    code = cup.strip().lower()
    if code not in EPICK_CUP_SPECS:
        raise ValueError(
            f"Unknown EPick cup code: {cup!r}. Use 's' (O40) or 'l' (O55)."
        )
    cup_kg, cup_m = EPICK_CUP_SPECS[code]
    cup_mm = cup_m * 1000.0

    mass_g = EPICK_BODY_MASS_KG * 1000.0
    cog_gmm = mass_g * EPICK_BODY_COG_Z_MM
    mount_top_mm = (
        EPICK_BODY_TCP_Z_MM
        if key == "single"
        else EPICK_BODY_TCP_Z_MM + EPICK_BRACKET_STACK_MM
    )
    if bracket_kg > 0.0:
        bracket_g = bracket_kg * 1000.0
        mass_g += bracket_g
        cog_gmm += bracket_g * bracket_cog_mm
    cup_g = cup_kg * 1000.0
    cup_center_mm = mount_top_mm + cup_mm / 2.0
    mass_g += count * cup_g
    cog_gmm += count * cup_g * cup_center_mm

    return GripperPreset(
        name=f"EPick-{key}-{code.upper()}",
        mass=round(mass_g / 1000.0, 3),
        center_of_gravity=[0.0, 0.0, round(cog_gmm / mass_g / 1000.0, 4)],
        tcp_offset=[0.0, 0.0, round((mount_top_mm + cup_mm) / 1000.0, 3), 0.0, 0.0, 0.0],
        backend="epick",
        max_mm=0,
        force=60,
        speed=30,
    )


# All six bracket + cup-size combinations, built from the component
# model above.  Name pattern: EPick-<system>-<cup>, e.g. config/CLI
# name "epick-quad-l".
ROBOTIQ_EPICK_SINGLE_S = _epick_preset("single", "s")
ROBOTIQ_EPICK_SINGLE_L = _epick_preset("single", "l")
ROBOTIQ_EPICK_DUAL_S = _epick_preset("dual", "s")
ROBOTIQ_EPICK_DUAL_L = _epick_preset("dual", "l")
ROBOTIQ_EPICK_QUAD_S = _epick_preset("quad", "s")
ROBOTIQ_EPICK_QUAD_L = _epick_preset("quad", "l")

# ---------------------------------------------------------------------------
# Registry — all built-in presets
# ---------------------------------------------------------------------------

PRESETS: dict[str, GripperPreset] = {
    p.name.upper(): p
    for p in (
        ROBOTIQ_2F_85,
        ROBOTIQ_2F_140,
        ROBOTIQ_HAND_E,
        ROBOTIQ_EPICK_SINGLE_S,
        ROBOTIQ_EPICK_SINGLE_L,
        ROBOTIQ_EPICK_DUAL_S,
        ROBOTIQ_EPICK_DUAL_L,
        ROBOTIQ_EPICK_QUAD_S,
        ROBOTIQ_EPICK_QUAD_L,
    )
}
"""Lookup dict keyed by uppercase preset name."""
