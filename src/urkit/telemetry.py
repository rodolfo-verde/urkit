"""Telemetry data retrieval from Universal Robots e-Series.

Reads TCP pose, joint positions, and force/torque sensor data
via the RTDE receive interface.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from urkit.exceptions import TelemetryError

if TYPE_CHECKING:
    from rtde_receive import RTDEReceiveInterface

logger = logging.getLogger(__name__)


class Telemetry:
    """Reads real-time telemetry data from the robot via RTDE.

    Wraps the RTDEReceiveInterface with typed, documented accessors.
    All methods raise TelemetryError if data cannot be read.

    Args:
        rtde_receive: RTDEReceiveInterface instance from ur_rtde.

    Example:
        >>> tel = Telemetry(rtde_r)
        >>> pose = tel.get_tcp_pose()
        >>> joints = tel.get_joint_positions()
        >>> force = tel.get_tcp_force()
    """

    def __init__(self, rtde_receive: "RTDEReceiveInterface") -> None:
        self._rtde_r = rtde_receive

    def get_tcp_pose(self) -> list[float]:
        """Get the current TCP pose in the base coordinate frame.

        Returns:
            List of 6 floats: [x, y, z, rx, ry, rz] in meters and radians.

        Raises:
            TelemetryError: If the pose cannot be read.
        """
        try:
            pose = self._rtde_r.getActualTCPPose()
            return list(pose)
        except Exception as e:
            raise TelemetryError(
                f"Failed to read TCP pose: {e}"
            )

    def get_joint_positions(self) -> list[float]:
        """Get the current joint positions.

        Returns:
            List of 6 floats: joint angles in radians [j0, j1, j2, j3, j4, j5].

        Raises:
            TelemetryError: If joint positions cannot be read.
        """
        try:
            joints = self._rtde_r.getActualQ()
            return list(joints)
        except Exception as e:
            raise TelemetryError(
                f"Failed to read joint positions: {e}"
            )

    def get_tcp_force(self) -> list[float]:
        """Get the current force/torque reading at the TCP.

        Returns:
            List of 6 floats: [fx, fy, fz, mx, my, mz] in N and Nm.

        Raises:
            TelemetryError: If force/torque cannot be read.
        """
        try:
            force = self._rtde_r.getActualTCPForce()
            return list(force)
        except Exception as e:
            raise TelemetryError(
                f"Failed to read TCP force: {e}"
            )

    def is_protective_stopped(self) -> bool:
        """Check if the robot is in protective stop state.

        Returns:
            True if the robot is protective stopped.
        """
        try:
            return bool(self._rtde_r.isProtectiveStopped())
        except Exception:
            return False

    def is_emergency_stopped(self) -> bool:
        """Check if the robot is in emergency stop state.

        Returns:
            True if the robot is emergency stopped.
        """
        try:
            return bool(self._rtde_r.isEmergencyStopped())
        except Exception:
            return False

    def get_speed_scaling(self) -> float:
        """Get the current speed scaling factor.

        Returns the trajectory limiter speed scaling, which indicates
        what fraction of the programmed speed the robot is actually
        running at. This value can be lower than the slider setting
        due to safety limits, blending, or other constraints.

        Returns:
            Speed scaling as a float between 0.0 and 1.0.

        Raises:
            TelemetryError: If speed scaling cannot be read.
        """
        try:
            return float(self._rtde_r.getSpeedScaling())
        except Exception as e:
            raise TelemetryError(
                f"Failed to read speed scaling: {e}"
            )

    def get_payload(self) -> float:
        """Get the currently configured payload mass.

        Returns:
            Payload mass in kg.

        Raises:
            TelemetryError: If the payload cannot be read.
        """
        try:
            return float(self._rtde_r.getPayload())
        except Exception as e:
            raise TelemetryError(
                f"Failed to read payload: {e}"
            )

    def get_speed_slider(self) -> float:
        """Get the current speed slider setting.

        Returns the configured speed slider value (the hardware
        multiplier), not the actual speed scaling. This is the value
        set by setSpeedSlider() or the physical pendant slider.

        Returns:
            Speed slider as a float between 0.0 and 1.0.

        Raises:
            TelemetryError: If speed slider cannot be read.
        """
        try:
            return float(self._rtde_r.getTargetSpeedFraction())
        except Exception as e:
            raise TelemetryError(
                f"Failed to read speed slider: {e}"
            )

    def get_robot_mode(self) -> str:
        """Get the current robot mode.

        Returns:
            String describing the robot mode (e.g., "NO_CONTROLLER",
            "DISCONNECTED", "CONFIRM_SAFETY", "FREEDRIVE", "SERVOING",
            "ROBOT_OFF", "REMOTE_CONTROL").

        Raises:
            TelemetryError: If the robot mode cannot be read.
        """
        try:
            mode = self._rtde_r.getRobotMode()
            # ur_rtde returns an integer for robot mode
            mode_map = {
                0: "NO_CONTROLLER",
                1: "DISCONNECTED",
                2: "CONFIRM_SAFETY",
                3: "FREEDRIVE",
                4: "SERVOING",
                5: "ROBOT_OFF",
                6: "REMOTE_CONTROL",
                7: "UPDATING_FLASH",
            }
            return mode_map.get(mode, f"UNKNOWN({mode})")
        except Exception as e:
            raise TelemetryError(
                f"Failed to read robot mode: {e}"
            )
