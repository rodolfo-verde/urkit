"""Motion commands for Universal Robots e-Series.

Provides joint moves (moveJ), linear moves (moveL), and relative
Cartesian moves via the RTDE control interface. All methods support per-call
velocity and acceleration override.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import contextmanager
from enum import IntEnum
from typing import TYPE_CHECKING

from urkit.exceptions import MotionError
from urkit.geometry import MoveFrame, transform_pose_delta


@contextmanager
def _suppress_rtde_stderr():
    """Temporarily redirect stderr to /dev/null.

    The ur_rtde C++ library prints "RTDE control script is not running!"
    to raw stderr (fd 2) on every call when the script is stopped.
    This context manager suppresses those messages by redirecting fd 2
    around the call.
    """
    devnull = os.open(os.devnull, os.O_WRONLY)
    old_stderr = os.dup(2)
    try:
        os.dup2(devnull, 2)
        sys.stderr.flush()
        yield
    finally:
        os.dup2(old_stderr, 2)
        os.close(old_stderr)
        os.close(devnull)

if TYPE_CHECKING:
    from rtde_control import RTDEControlInterface
    from rtde_io import RTDEIOInterface
    from rtde_receive import RTDEReceiveInterface

logger = logging.getLogger(__name__)

# URScript axis order for delta move commands:
# 0=X, 1=Y, 2=Z, 3=Roll, 4=Pitch, 5=Yaw
_AXIS_LABELS = ["X", "Y", "Z", "Roll", "Pitch", "Yaw"]


class FreedriveMode(IntEnum):
    """Freedrive axis selection mode.

    Controls which axes the robot allows manual movement on.
    """

    ALL = 0  # All 6 axes free
    XYZ = 1  # Linear axes (X, Y, Z) + rotation around Z (Rz)
    ROTATION = 2  # Only rotational axes (Roll, Pitch, Yaw)


class Motion:
    """Motion commands via RTDE control interface.

    Wraps the RTDEControlInterface with typed, documented motion
    primitives. All methods raise MotionError on failure.

    Args:
        rtde_control: RTDEControlInterface instance.
        rtde_receive: RTDEReceiveInterface instance (for current pose reads).
        rtde_io: RTDEIOInterface instance (for speed slider control).
        default_vel: Default linear velocity (m/s) for move commands.
        default_acc: Default linear acceleration (m/s²) for move commands.

    Example:
        >>> motion = Motion(rtde_c, rtde_r, rtde_io, default_vel=0.5, default_acc=0.3)
        >>> motion.movej([0, -1.57, 0, -1.57, 0, 0])
        >>> motion.movel([0.5, 0, 0.3, 0, 0, 0])
        >>> motion.move_by([0.01, 0, 0, 0, 0, 0])
    """

    def __init__(
        self,
        rtde_control: "RTDEControlInterface",
        rtde_receive: "RTDEReceiveInterface",
        rtde_io: "RTDEIOInterface",
        default_vel: float = 0.5,
        default_acc: float = 0.3,
    ) -> None:
        if default_vel <= 0:
            raise MotionError(
                f"default_vel must be > 0, got {default_vel}."
            )
        if default_acc <= 0:
            raise MotionError(
                f"default_acc must be > 0, got {default_acc}."
            )
        self._rtde_c = rtde_control
        self._rtde_r = rtde_receive
        self._rtde_io = rtde_io
        self._default_vel = default_vel
        self._default_acc = default_acc
        self._freedrive_active = False

    @property
    def is_freedrive_active(self) -> bool:
        """Return whether freedrive is currently active."""
        return self._freedrive_active

    def movej(
        self,
        joints: list[float],
        vel: float | None = None,
        acc: float | None = None,
    ) -> None:
        """Move to target joint configuration.

        Uses URScript movej() for joint-space interpolation.

        Args:
            joints: 6 joint angles in radians [j0, j1, j2, j3, j4, j5].
            vel: Linear velocity (m/s). Falls back to default_vel.
            acc: Linear acceleration (m/s²). Falls back to default_acc.

        Raises:
            MotionError: If the move fails.
        """
        if len(joints) != 6:
            raise MotionError(
                f"Joint move requires 6 values, got {len(joints)}."
            )
        vel = vel if vel is not None else self._default_vel
        acc = acc if acc is not None else self._default_acc

        try:
            if not self._rtde_c.isConnected():
                raise MotionError(
                    "RTDE connection lost. The robot may have faulted. "
                    "Reconnect or reinitialize the robot."
                )
            logger.debug(
                "movej: joints=%s, vel=%.3f, acc=%.3f", joints, vel, acc
            )
            with _suppress_rtde_stderr():
                self._rtde_c.moveJ(joints, vel, acc)
        except MotionError:
            raise
        except Exception as e:
            raise MotionError(
                f"Joint move failed: {e}"
            )

    def movel(
        self,
        pose: list[float],
        vel: float | None = None,
        acc: float | None = None,
    ) -> None:
        """Move in a straight line to target TCP pose.

        Uses URScript movel() for Cartesian linear interpolation.

        Args:
            pose: 6 floats [x, y, z, rx, ry, rz] in meters/radians.
            vel: Linear velocity (m/s). Falls back to default_vel.
            acc: Linear acceleration (m/s²). Falls back to default_acc.

        Raises:
            MotionError: If the move fails.
        """
        if len(pose) != 6:
            raise MotionError(
                f"Linear move requires 6 values [x,y,z,rx,ry,rz], got {len(pose)}."
            )
        vel = vel if vel is not None else self._default_vel
        acc = acc if acc is not None else self._default_acc

        try:
            if not self._rtde_c.isConnected():
                raise MotionError(
                    "RTDE connection lost. The robot may have faulted. "
                    "Reconnect or reinitialize the robot."
                )
            logger.debug(
                "movel: pose=%s, vel=%.3f, acc=%.3f", pose, vel, acc
            )
            with _suppress_rtde_stderr():
                self._rtde_c.moveL(pose, vel, acc)
        except MotionError:
            raise
        except Exception as e:
            raise MotionError(
                f"Linear move failed: {e}"
            )

    def move_by(
        self,
        delta: list[float],
        vel: float | None = None,
        acc: float | None = None,
        frame: MoveFrame = MoveFrame.BASE,
    ) -> None:
        """Execute a relative Cartesian linear move.

        Reads the current TCP pose, transforms the delta according to
        the given frame of reference, and moves linearly to the
        resulting pose.

        Args:
            delta: 6 floats [dx, dy, dz, droll, dpitch, dyaw].
            vel: Linear velocity (m/s). Falls back to default_vel.
            acc: Linear acceleration (m/s²). Falls back to default_acc.
            frame: Coordinate frame for interpreting the delta
                (``MoveFrame.BASE`` or ``MoveFrame.TOOL``).

        Raises:
            MotionError: If the move fails.
        """
        if len(delta) != 6:
            raise MotionError(
                f"Relative move requires 6 values [dx,dy,dz,droll,dpitch,dyaw], "
                f"got {len(delta)}."
            )
        vel = vel if vel is not None else self._default_vel
        acc = acc if acc is not None else self._default_acc

        try:
            if not self._rtde_c.isConnected():
                raise MotionError(
                    "RTDE connection lost. The robot may have faulted. "
                    "Reconnect or reinitialize the robot."
                )
            current = list(self._rtde_r.getActualTCPPose())
            target = transform_pose_delta(current, delta, frame)
            logger.debug(
                "move_by: current=%s, target=%s, frame=%s, vel=%.3f, acc=%.3f",
                current, target, frame.name, vel, acc,
            )
            with _suppress_rtde_stderr():
                self._rtde_c.moveL(target, vel, acc)
        except MotionError:
            raise
        except Exception as e:
            raise MotionError(
                f"Relative move failed: {e}"
            )

    def move_until_contact(
        self,
        speed_vector: list[float],
        *,
        threshold: float = 5.0,
        acceleration: float = 0.1,
    ) -> None:
        """Move until contact is detected via TCP force sensing.

        Runs a 500 Hz control loop that sends ``speedL()`` commands and
        checks the tool force/torque on every iteration. Unlike the
        native ``moveUntilContact`` URScript command, this wrapper is
        interruptible with ``KeyboardInterrupt`` (Ctrl+C) because the
        contact check happens in Python each cycle.

        Accepts a full 6-element speed vector so the caller controls
        every axis — linear and rotational.

        Args:
            speed_vector: 6-element speed vector
                ``[vx, vy, vz, vRoll, vPitch, dYaw]`` in m/s and rad/s.
            threshold: Force/torque delta (N or Nm) that triggers contact.
                Contact fires when any of the 6 wrench components changes
                by more than this value from the baseline reading.
            acceleration: Acceleration limit passed to ``speedL()`` in m/s².

        Raises:
            MotionError: If the command fails or the vector is invalid.

        Example:
            >>> # Move straight down until contact
            >>> motion.move_until_contact([0, 0, -0.02, 0, 0, 0])
            >>> # Move down while rotating, higher threshold
            >>> motion.move_until_contact([0, 0, -0.02, 0, 0.1, 0], threshold=10.0)
        """
        if len(speed_vector) != 6:
            raise MotionError(
                f"Speed vector must have 6 values, got {len(speed_vector)}."
            )
        if threshold <= 0:
            raise MotionError(f"Threshold must be > 0, got {threshold}.")

        try:
            logger.debug(
                "move_until_contact: speed_vector=%s, threshold=%.2f",
                speed_vector, threshold,
            )

            # Baseline force reading before the loop
            baseline = list(self._rtde_r.getActualTCPForce())

            while True:
                if not self._rtde_c.isConnected():
                    raise MotionError(
                        "RTDE connection lost during move_until_contact. "
                        "The robot may have faulted or the script stopped."
                    )
                # Check robot safety state (cached data, non-blocking)
                try:
                    if self._rtde_r.isProtectiveStopped():
                        raise MotionError(
                            "Robot is in protective stop. "
                            "Clear the stop and reinitialize."
                        )
                    if self._rtde_r.isEmergencyStopped():
                        raise MotionError(
                            "Robot is in emergency stop. "
                            "Clear the stop and reinitialize."
                        )
                except MotionError:
                    raise
                except Exception:
                    pass  # Telemetry read failed, continue

                with _suppress_rtde_stderr():
                    t_start = self._rtde_c.initPeriod()
                    self._rtde_c.speedL(speed_vector, acceleration, 0.002)

                # Check force/torque for contact
                current = list(self._rtde_r.getActualTCPForce())
                if any(
                    abs(current[i] - baseline[i]) > threshold for i in range(6)
                ):
                    break

                with _suppress_rtde_stderr():
                    self._rtde_c.waitPeriod(t_start)
        except MotionError:
            raise
        except Exception as e:
            raise MotionError(f"move_until_contact failed: {e}")
        finally:
            try:
                with _suppress_rtde_stderr():
                    self._rtde_c.speedStop()
            except Exception:
                pass

    def move_velocity(
        self,
        speed_vector: list[float],
        duration: float,
        acceleration: float = 0.1,
        dt: float = 0.002,
    ) -> None:
        """Move at a constant Cartesian velocity for a given duration.

        Runs a 500 Hz control loop that sends ``speedL()`` commands.
        Blocks until *duration* seconds have elapsed.

        Args:
            speed_vector: 6-element Cartesian velocity
                ``[vx, vy, vz, vRoll, vPitch, dYaw]`` in m/s and rad/s.
            duration: How long to move in seconds.
            acceleration: Acceleration limit in m/s\ :sup:2.
            dt: Control loop period in seconds (default 0.002 = 500 Hz).

        Raises:
            MotionError: If the command fails.

        Example:
            >>> # Move down at 20 mm/s for 1 second
            >>> motion.move_velocity([0, 0, -0.02, 0, 0, 0], duration=1.0)
        """
        if len(speed_vector) != 6:
            raise MotionError(
                f"Speed vector must have 6 values, got {len(speed_vector)}."
            )
        if duration <= 0:
            raise MotionError(f"Duration must be > 0, got {duration}.")

        try:
            import time as _time

            start = _time.monotonic()
            while True:
                elapsed = _time.monotonic() - start
                if elapsed >= duration:
                    break
                if not self._rtde_c.isConnected():
                    raise MotionError(
                        "RTDE connection lost during move_velocity. "
                        "The robot may have faulted or the script stopped."
                    )
                # Check robot safety state (cached data, non-blocking)
                try:
                    if self._rtde_r.isProtectiveStopped():
                        raise MotionError(
                            "Robot is in protective stop. "
                            "Clear the stop and reinitialize."
                        )
                    if self._rtde_r.isEmergencyStopped():
                        raise MotionError(
                            "Robot is in emergency stop. "
                            "Clear the stop and reinitialize."
                        )
                except MotionError:
                    raise
                except Exception:
                    pass  # Telemetry read failed, continue

                with _suppress_rtde_stderr():
                    t_start = self._rtde_c.initPeriod()
                    self._rtde_c.speedL(speed_vector, acceleration, dt)
                    self._rtde_c.waitPeriod(t_start)
        except MotionError:
            raise
        except Exception as e:
            raise MotionError(f"move_velocity failed: {e}")
        finally:
            try:
                with _suppress_rtde_stderr():
                    self._rtde_c.speedStop()
            except Exception:
                pass

    def speed_stop(self) -> None:
        """Stop any ongoing speed motion immediately.

        Used to halt speed-based operations.
        """
        try:
            with _suppress_rtde_stderr():
                self._rtde_c.speedStop()
        except Exception as e:
            logger.warning("speedStop failed: %s", e)

    def stop_script(self) -> None:
        """Stop the running URScript program."""
        try:
            with _suppress_rtde_stderr():
                self._rtde_c.stopScript()
        except Exception as e:
            logger.warning("stopScript failed: %s", e)

    def set_speed_slider(self, factor: float) -> None:
        """Set the speed slider factor for subsequent motions.

        Args:
            factor: Speed factor 0.0–1.0.

        Raises:
            MotionError: If the setting fails.
        """
        if not 0.0 <= factor <= 1.0:
            raise MotionError(
                f"Speed slider factor must be 0.0–1.0, got {factor}."
            )
        try:
            self._rtde_io.setSpeedSlider(factor)
        except Exception as e:
            raise MotionError(
                f"Failed to set speed slider to {factor}: {e}"
            )

    def enable_freedrive(self, mode: FreedriveMode = FreedriveMode.ALL) -> None:
        """Enable freedrive mode for manual robot manipulation.

        Args:
            mode: Which axes to allow manual movement on.

        Raises:
            MotionError: If freedrive cannot be enabled.
        """
        try:
            if mode == FreedriveMode.ALL:
                free_axes = [1, 1, 1, 1, 1, 1]
            elif mode == FreedriveMode.XYZ:
                free_axes = [1, 1, 1, 0, 0, 1]
            elif mode == FreedriveMode.ROTATION:
                free_axes = [0, 0, 0, 1, 1, 1]
            else:
                raise MotionError(f"Unknown freedrive mode: {mode}")

            feature = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]  # base coordinate frame
            success = self._rtde_c.freedriveMode(free_axes, feature)
            if not success:
                raise MotionError(
                    f"freedriveMode returned false (mode={mode.name})"
                )
            self._freedrive_active = True
            logger.info("Freedrive mode enabled (%s)", mode.name)
        except Exception as e:
            raise MotionError(
                f"Failed to enable freedrive mode: {e}"
            )

    def disable_freedrive(self) -> None:
        """Disable freedrive mode."""
        try:
            self._rtde_c.endFreedriveMode()
            self._freedrive_active = False
            logger.info("Freedrive mode disabled")
        except Exception as e:
            logger.warning("Failed to disable freedrive: %s", e)
