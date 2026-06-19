"""URRobot — the main robot class.

Ties together connection validation, motion, telemetry, I/O, gripper,
and named point management into a single high-level interface.
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from urkit.connection import (
    _check_remote_mode,
    _connect_dashboard,
    _connect_rtde,
    _dashboard_command,
    _get_safety_help_message,
    _try_recover_safety,
    _validate_connection,
)
from urkit.exceptions import GripperError, MotionError, PointError, URKitConnectionError as ConnectionError
from urkit.geometry import MoveFrame, transform_pose_delta
from urkit.gripper.base import Gripper
from urkit.gripper.presets import DigitalGripperConfig, GripperPreset, PRESETS
from urkit.io import IO
from urkit.motion import FreedriveMode, Motion
from urkit.points import Point, Points
from urkit.telemetry import Telemetry

logger = logging.getLogger(__name__)

# ANSI colors (auto-disabled when stdout isn't a TTY)
_use_color = sys.stdout.isatty()
_YELLOW = "\033[93m" if _use_color else ""
_GREEN  = "\033[92m" if _use_color else ""
_RESET  = "\033[0m"  if _use_color else ""


def _status(msg: str, done: bool = False) -> None:
    """Print a status message with color."""
    prefix = _GREEN + "✓ " if done else _YELLOW + "● "
    print(f"{prefix}{msg}{_RESET}", flush=True)


def _is_pose(v: object) -> bool:
    """Check if a value looks like a TCP pose (6-element numeric list)."""
    return (
        isinstance(v, (list, tuple))
        and len(v) == 6
        and all(isinstance(x, (int, float)) for x in v)
    )


class URRobot:
    """High-level interface to a Universal Robots e-Series robot.

    Manages the full lifecycle: connection validation, RTDE connection,
    robot startup (power on + brake release), TCP/payload setup, and
    provides unified access to motion, telemetry, I/O, gripper, and
    named point management.

    All motion commands support per-call velocity and acceleration
    override, falling back to the constructor defaults.

    Args:
        ip: Robot IP address.
        points: Path to the SQLite points database file. Created if it
            does not exist. Optional — named point operations
            (``save_point``, ``move_to("name")``, etc.) raise
            ``PointError`` if not set. Can be changed later via the
            ``points_db`` property.
        gripper: A :class:`~urkit.gripper.presets.GripperPreset` or
            :class:`~urkit.gripper.presets.DigitalGripperConfig`.
            Presets provide mass, CoG, TCP offset, and backend type.
        default_vel: Default linear velocity (m/s).
        default_acc: Default linear acceleration (m/s²).
        gripper_kwargs: Additional kwargs passed to the gripper backend
            to override preset values (e.g. ``max_mm=80`` for custom
            fingers, ``force=50``, ``speed=80`` for Robotiq).

    Example:
        >>> from urkit import URRobot, ROBOTIQ_2F_85
        >>> robot = URRobot(ip="192.168.1.100", gripper=ROBOTIQ_2F_85)
        >>> robot.move_relative([0.01, 0, 0, 0, 0, 0])  # works without points
        >>> robot.points_db = "points.db"  # set lazily
        >>> robot.save_point("home")
    """

    def __init__(
        self,
        ip: str,
        *,
        points: str | Path | None = None,
        gripper: GripperPreset | DigitalGripperConfig | None = None,
        default_vel: float = 0.5,
        default_acc: float = 0.3,
        **gripper_kwargs,
    ) -> None:
        self._ip = ip
        self._default_vel = default_vel
        self._default_acc = default_acc
        self._rtde_frequency = 500.0
        self._connection_lost = False
        self._move_frame: MoveFrame = MoveFrame.BASE

        # Points database (internal) — optional, lazy-initialized
        self._points: Points | None = Points(points) if points is not None else None

        # Resolve payload/CoG/TCP from gripper config.
        resolved_payload = 0.0
        resolved_cog: list[float] = [0.0, 0.0, 0.0]
        resolved_tcp: list[float] | None = None
        gripper_backend: str | None = None
        if isinstance(gripper, GripperPreset):
            resolved_payload = gripper.mass
            resolved_cog = list(gripper.center_of_gravity)
            resolved_tcp = list(gripper.tcp_offset)
            gripper_backend = gripper.backend
        # DigitalGripperConfig has no payload specs.

        # Validate connection (ping + ports)
        _validate_connection(ip)

        # Dashboard socket for lifecycle commands
        self._dashboard: object | None = None

        # Check remote mode — before any Dashboard commands
        if not _check_remote_mode(ip):
            raise ConnectionError(
                f"Robot at {ip} is not in remote control mode. "
                f"Enable it in Settings → System → Remote Control on the teach pendant."
            )
        logger.info("[URRobot] Remote mode OK")

        # Check safety status — ur_rtde segfaults on faulted robots
        # (C++ exception, uncatchable from Python). Fail early with a clear message.
        try:
            safety_ok, safety_status = _try_recover_safety(ip)
            if not safety_ok:
                help_msg = _get_safety_help_message(safety_status)
                raise ConnectionError(
                    f"Robot at {ip} is in an unrecoverable safety state: {safety_status}.\n"
                    f"{help_msg}"
                )
            if safety_status not in ("NORMAL", "REDUCED", "RECOVERY"):
                logger.info("[URRobot] Safety recovered from %s", safety_status)
        except ConnectionError:
            raise
        except Exception as e:
            # Dashboard unreachable for safety check — log and continue.
            logger.warning("[URRobot] Could not check safety status: %s", e)

        # Power on + release brakes — skip if the robot is already ready.
        # After a safety VIOLATION recovery the robot is POWER_OFF, so this
        # handles that case too.
        self._connect_dashboard()
        did_power_on = self.power_on()
        did_release = self.release_brakes()
        boot_needed = did_power_on or did_release

        # Settle after boot — the robot reports IDLE but the Secondary
        # Interface (RTDE) needs time to be ready for script upload.
        # Skip if the robot was already running.
        if boot_needed:
            time.sleep(5)

        # Stop any running program — RTDE cannot upload its control script
        # while a program is occupying the Secondary Interface. Only needed
        # after a boot (a program left running by another client is their problem).
        if boot_needed:
            try:
                self._stop_program()
                time.sleep(2)
            except ConnectionError:
                logger.warning(
                    "[URRobot] Could not stop program via Dashboard. "
                    "Continuing — RTDE connection may fail if a program is running."
                )

        # Connect RTDE
        self._rtde_c, self._rtde_r, self._rtde_io = _connect_rtde(
            ip,
            frequency=self._rtde_frequency,
        )

        # Initialize subsystems
        self._telemetry = Telemetry(self._rtde_r)
        self._io = IO(self._rtde_io, self._rtde_r)
        self._motion = Motion(
            self._rtde_c,
            self._rtde_r,
            self._rtde_io,
            default_vel=default_vel,
            default_acc=default_acc,
        )

        # Gripper
        self._gripper: Gripper | None = None
        if gripper_backend is not None:
            try:
                # Merge preset defaults with user overrides.
                if isinstance(gripper, GripperPreset):
                    effective_kwargs = {
                        "max_mm": gripper.max_mm,
                        "force": gripper.force,
                        "speed": gripper.speed,
                        **gripper_kwargs,
                    }
                else:
                    effective_kwargs = gripper_kwargs

                effective_kwargs["rtde_control"] = self._rtde_c
                effective_kwargs["rtde_receive"] = self._rtde_r
                effective_kwargs["robot_ip"] = self._ip
                self._gripper = Gripper.create(gripper_backend, **effective_kwargs)
            except Exception as e:
                logger.warning(
                    "Failed to create gripper (%s): %s. Continuing without.",
                    gripper_backend, e,
                )
        elif isinstance(gripper, DigitalGripperConfig):
            try:
                self._gripper = Gripper.create(
                    "digital",
                    rtde_control=self._rtde_c,
                    rtde_receive=self._rtde_r,
                    robot_ip=self._ip,
                    pin=gripper.pin,
                    closed_when_high=gripper.close_on_high,
                    **gripper_kwargs,
                )
            except Exception as e:
                logger.warning(
                    "Failed to create digital gripper: %s. Continuing without.", e,
                )

        # Set TCP offset and payload (resolved values)
        if resolved_tcp is not None:
            self.set_tcp_offset(resolved_tcp)
        if resolved_payload > 0:
            self.set_payload(resolved_payload, resolved_cog)

        logger.info("URRobot initialized at %s", ip)

    def activate_gripper(self, *, timeout: float = 5.0) -> bool:
        """Activate the gripper with a timeout.

        Tries to activate the configured gripper. If activation fails
        or times out (e.g., gripper not physically connected), disconnects
        the gripper, nulls out ``self._gripper``, and returns ``False``.

        This is the single place that handles gripper activation — the
        CLI and library code should call this rather than touching
        ``gripper.activate()`` directly.

        Args:
            timeout: Maximum seconds to wait for activation (default 5.0).

        Returns:
            ``True`` if the gripper was activated successfully,
            ``False`` if no gripper is configured or activation failed.
        """
        if self._gripper is None:
            return False

        try:
            self._gripper.activate(timeout=timeout)
        except GripperError as e:
            _status(f"Gripper activation failed: {e}", done=False)
            # Reconnect RTDE to kill the stuck daemon thread — it's blocked
            # on sendCustomScriptFunction running a 2000-iteration loop on
            # the robot. Tearing down the socket kills it immediately.
            _gripper = self._gripper
            self._gripper = None
            try:
                _gripper.disconnect()
            except Exception:
                pass
            try:
                self.reconnect_rtde()
            except ConnectionError:
                logger.warning("Failed to reconnect RTDE after gripper timeout")
            return False

        return True

    @classmethod
    def from_config(
        cls,
        config: str | dict,
        *,
        ip: str | None = None,
        points: str | Path | None = None,
        gripper: GripperPreset | DigitalGripperConfig | str | None = None,
        default_vel: float | None = None,
        default_acc: float | None = None,
        **gripper_kwargs,
    ) -> "URRobot":
        """Create a URRobot from a YAML config file or dict.

        Explicit keyword arguments override values from the config file,
        which override the URRobot constructor defaults.

        Args:
            config: Path to a YAML file (str) or a dict with config keys.
            ip: Robot IP address. Overrides ``robot_ip`` from config.
            points: Path to points database. Overrides ``points_path`` from config.
            gripper: A GripperPreset, DigitalGripperConfig, a preset name
                string (e.g. ``"hand-e"``, ``"2f-85"``, ``"digital"``),
                or ``None``. Overrides the ``gripper`` key from config.
            default_vel: Default linear velocity (m/s).
            default_acc: Default linear acceleration (m/s²).
            gripper_kwargs: Overrides for gripper preset values
                (e.g. ``max_mm``, ``force``, ``speed``, ``pin``).

        Config file keys::

            robot_ip: 172.31.1.200
            points_path: points.db
            gripper: hand-e
            default_vel: 0.5
            default_acc: 0.3
            rtde_frequency: 500

        Example:
            >>> robot = URRobot.from_config("config.yaml")
            >>> robot = URRobot.from_config("config.yaml", ip="10.0.0.50")
            >>> robot = URRobot.from_config({"robot_ip": "172.31.1.200", "points_path": "points.db", "gripper": "2f-85"})
        """
        from urkit.config import load_config, resolve_config

        if isinstance(config, str):
            resolved = resolve_config(config)
            if resolved is None:
                raise ValueError(f"Config file not found: {config!r}")
            try:
                import yaml as _yaml
                with open(resolved, "r") as f:
                    cfg: dict = _yaml.safe_load(f) or {}
            except Exception as e:
                raise ValueError(f"Failed to parse config {resolved}: {e}")
            if not isinstance(cfg, dict):
                raise ValueError(f"Config must be a YAML mapping, got {type(cfg).__name__}")
        else:
            cfg = config

        # Resolve each parameter: explicit kwarg > config > default
        resolved_ip: str | None = ip or cfg.get("robot_ip")
        if not resolved_ip:
            raise ValueError(
                "Robot IP is required. Pass it as the 'ip' argument, "
                "or set 'robot_ip' in the config file."
            )

        resolved_points: str | Path | None = points or cfg.get("points_path")

        # Resolve gripper
        resolved_gripper: GripperPreset | DigitalGripperConfig | None = None
        gripper_source = gripper or cfg.get("gripper")
        if gripper_source is not None:
            if isinstance(gripper_source, (GripperPreset, DigitalGripperConfig)):
                resolved_gripper = gripper_source
            elif isinstance(gripper_source, str):
                key = gripper_source.strip().upper()
                preset = PRESETS.get(key)
                if preset is not None:
                    resolved_gripper = preset
                elif gripper_source.strip().lower() == "digital":
                    resolved_gripper = DigitalGripperConfig(
                        pin=gripper_kwargs.get("pin", 0),
                        close_on_high=gripper_kwargs.get("close_on_high", True),
                    )
                else:
                    raise ValueError(
                        f"Unknown gripper preset: {gripper_source!r}. "
                        f"Available: {', '.join(sorted(PRESETS.keys()))}, 'digital'."
                    )

        # Merge config gripper overrides into gripper_kwargs
        gripper_overrides = ("max_mm", "force", "speed", "pin", "close_on_high")
        for key in gripper_overrides:
            if key not in gripper_kwargs and key in cfg:
                gripper_kwargs[key] = cfg[key]

        return cls(
            ip=resolved_ip,
            points=resolved_points,
            gripper=resolved_gripper,
            default_vel=default_vel if default_vel is not None else cfg.get("default_vel", 0.5),
            default_acc=default_acc if default_acc is not None else cfg.get("default_acc", 0.3),
            **gripper_kwargs,
        )

    @property
    def ip(self) -> str:
        """Robot IP address."""
        return self._ip

    @property
    def gripper(self) -> Gripper | None:
        """Gripper instance, or None if not configured."""
        return self._gripper

    @property
    def connection_lost(self) -> bool:
        """True if the RTDE connection dropped during operation."""
        return self._connection_lost

    @property
    def move_frame(self) -> MoveFrame:
        """Current coordinate frame for relative (delta) movements and offsets.

        Controls how delta vectors and offsets are interpreted:
        - ``MoveFrame.BASE`` — relative to the robot base (default).
        - ``MoveFrame.TOOL`` — relative to the current TCP orientation.

        This is the default for ``move_to(offset=)``, ``move_relative()``,
        and any method that applies a spatial delta. Individual calls can
        override with their own ``frame=`` argument.

        Example:
            >>> robot.move_frame = MoveFrame.TOOL
            >>> robot.move_relative([0.01, 0, 0, 0, 0, 0])  # +X in tool frame
            >>> robot.move_to("pick", offset=[0, 0, 0.05])   # offset in tool frame
        """
        return self._move_frame

    @move_frame.setter
    def move_frame(self, value: MoveFrame) -> None:
        self._move_frame = MoveFrame(value)

    @property
    def points_db(self) -> Points | None:
        """Points database instance, or None if not set.

        Can be used to set or change the points database at runtime.

        Example:
            >>> robot.points_db = "points.db"       # initialize
            >>> robot.points_db = "other_workcell.db"  # swap
            >>> robot.points_db = None               # unset
        """
        return self._points

    @points_db.setter
    def points_db(self, path: str | Path | None) -> None:
        if self._points is not None:
            self._points._close()
        self._points = Points(path) if path is not None else None

    def _require_points(self) -> Points:
        """Return the Points instance, or raise PointError if not set."""
        if self._points is None:
            raise PointError(
                "No points database configured. "
                "Pass points=... to the constructor, or set robot.points_db = 'path.db'."
            )
        return self._points

    # ------------------------------------------------------------------
    # Access to raw ur_rtde interfaces (advanced use)
    # ------------------------------------------------------------------

    @property
    def rtde_control(self) -> "RTDEControlInterface":
        """Raw ur_rtde RTDEControlInterface for advanced use.

        Gives direct access to ur_rtde methods not wrapped by urkit
        (e.g. ``moveUntilContact``, ``forceMode``, ``servoJ``).
        """
        return self._rtde_c

    @property
    def rtde_receive(self) -> "RTDEReceiveInterface":
        """Raw ur_rtde RTDEReceiveInterface for advanced use.

        Gives direct access to ur_rtde receive methods not wrapped by urkit
        (e.g. ``getActualCurrent``, ``getStandardAnalogInput``).
        """
        return self._rtde_r

    # ------------------------------------------------------------------
    # Dashboard / lifecycle
    # ------------------------------------------------------------------

    def _connect_dashboard(self) -> None:
        """Open a Dashboard socket if not already connected."""
        if self._dashboard is None:
            try:
                self._dashboard = _connect_dashboard(self._ip)
            except ConnectionError:
                logger.warning(
                    "Could not connect to Dashboard at %s:29999. "
                    "Power-on and brake-release may fail.",
                    self._ip,
                )

    def _send_dashboard(self, command: str) -> str:
        """Send a command via Dashboard and return the response."""
        if self._dashboard is None:
            self._connect_dashboard()
        if self._dashboard is None:
            raise ConnectionError(
                "Dashboard connection not available. "
                "Cannot execute command: " + command
            )
        return _dashboard_command(self._dashboard, command)

    def _poll_robotmode(
        self,
        predicate,
        *,
        timeout: float = 30.0,
        interval: float = 0.5,
    ) -> str:
        """Poll Dashboard ``robotmode`` until *predicate(mode)* is True.

        Args:
            predicate: Callable that returns True when the desired mode is reached.
            timeout: Maximum time to wait in seconds.
            interval: Seconds between polls.

        Returns:
            The final robotmode string.

        Raises:
            ConnectionError: If the timeout is reached.
        """
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                mode = self._send_dashboard("robotmode")
                if predicate(mode):
                    return mode
            except ConnectionError:
                # Dashboard may flicker during state transitions
                pass
            time.sleep(interval)
        raise ConnectionError(
            f"Robot did not reach desired mode within {timeout:.0f}s"
        )

    def power_on(self) -> bool:
        """Power on the robot.

        Checks the current robot mode first. If the robot is already
        powered on (not in POWER_OFF), the command is skipped silently.

        Polls until the robot is no longer in POWER_OFF mode.

        Returns:
            True if the robot was actually powered on, False if it was
            already powered on.

        Raises:
            ConnectionError: If power-on fails or times out.
        """
        try:
            # Check current mode first — skip if already powered on.
            mode = self._send_dashboard("robotmode").upper()
            if "POWER_OFF" not in mode and "NO_CONNECTION" not in mode:
                logger.info("Robot already powered on (mode: %s), skipping.", mode)
                return False

            response = self._send_dashboard("power on")
            logger.info("Power on: %s", response)
            if "Powering on" in response:
                _status("Powering on robot...", done=False)
                logger.info("Robot powering on, waiting for ready state...")
                self._poll_robotmode(
                    lambda m: "POWER_OFF" not in m.upper(),
                    timeout=30.0,
                )
                _status("Robot powered on", done=True)
                return True
            elif "Robot is already powered on" in response:
                return False
            else:
                raise ConnectionError(f"Power on unexpected response: {response}")
        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"Power on failed: {e}")

    def power_off(self) -> None:
        """Power off the robot.

        Raises:
            ConnectionError: If power-off fails.
        """
        try:
            response = self._send_dashboard("power off")
            logger.info("Power off: %s", response)
        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"Power off failed: {e}")

    def release_brakes(self) -> bool:
        """Release the robot brakes (enable control).

        Checks the current robot mode first. If the robot is already
        in IDLE or RUNNING, the command is skipped silently.

        Polls until the robot reports IDLE or RUNNING mode.

        Returns:
            True if the brakes were actually released, False if they
            were already released.

        Raises:
            ConnectionError: If brake release fails or times out.
        """
        try:
            # Check current mode first — skip if already released.
            mode = self._send_dashboard("robotmode").upper()
            if "IDLE" in mode or "RUNNING" in mode:
                logger.info("Brakes already released (mode: %s), skipping.", mode)
                return False

            response = self._send_dashboard("brake release")
            logger.info("Brake release: %s", response)
            if "Brake releasing" in response:
                _status("Releasing brakes...", done=False)
                logger.info("Brakes releasing, waiting for ready state...")
                self._poll_robotmode(
                    lambda m: "IDLE" in m.upper() or "RUNNING" in m.upper(),
                    timeout=30.0,
                )
                _status("Brakes released", done=True)
                return True
            elif "Brake is already releasing" in response:
                return False
            else:
                raise ConnectionError(
                    f"Brake release unexpected response: {response}"
                )
        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"Brake release failed: {e}")

    def recover(self) -> None:
        """Recover from protective stop or safety stop.

        Sends the "clear protective stop" command to the Dashboard.

        Raises:
            ConnectionError: If recovery fails.
        """
        try:
            response = self._send_dashboard("clear protective stop")
            logger.info("Recover: %s", response)
        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"Recovery failed: {e}")

    def is_remote_mode(self) -> bool:
        """Check if the robot is in remote control mode.

        Uses the Dashboard command 'is in remote control' which returns
        'True'/'False' regardless of whether a program is running. The
        'robotmode' command only mentions "remote control" when a remote
        program is actively executing — returning 'IDLE' when the robot
        is idle, even if remote control is enabled.

        Returns:
            True if in remote control mode.
        """
        try:
            if self._dashboard is None:
                self._connect_dashboard()
            if self._dashboard is None:
                return False
            response = _dashboard_command(self._dashboard, "is in remote control")
            return response.strip().lower() == "true"
        except Exception:
            return False

    def _stop_program(self) -> None:
        """Stop the running program via the Dashboard socket."""
        if self._dashboard is None:
            self._connect_dashboard()
        if self._dashboard is None:
            raise ConnectionError(
                "Dashboard connection not available. Cannot stop program."
            )
        response = _dashboard_command(self._dashboard, "stop")
        logger.info("Dashboard 'stop' response: %s", response)

    # ------------------------------------------------------------------
    # TCP / payload setup
    # ------------------------------------------------------------------

    def set_tcp_offset(self, tcp_offset: list[float]) -> None:
        """Set the TCP offset (tool frame).

        Args:
            tcp_offset: [x, y, z, rx, ry, rz] in meters/radians.

        Raises:
            MotionError: If the TCP offset cannot be set.
        """
        if len(tcp_offset) != 6:
            raise MotionError(
                f"TCP offset must have 6 values, got {len(tcp_offset)}."
            )
        try:
            self._rtde_c.setTcp(list(tcp_offset))
            logger.info("TCP offset set to %s", tcp_offset)
        except Exception as e:
            raise MotionError(f"Failed to set TCP offset: {e}")

    def set_payload(self, mass: float, center_of_gravity: list[float] | None = None) -> None:
        """Set the tool payload mass and center of gravity.

        Args:
            mass: Mass in kg.
            center_of_gravity: Center of gravity in tool coordinates
                [x, y, z] in meters (default [0, 0, 0]).

        Raises:
            MotionError: If the payload cannot be set.
        """
        if mass < 0:
            raise MotionError(f"Payload mass must be >= 0, got {mass}.")
        cog = center_of_gravity if center_of_gravity is not None else [0.0, 0.0, 0.0]
        if len(cog) != 3:
            raise MotionError(f"Center of gravity must have 3 values, got {len(cog)}.")
        try:
            self._rtde_c.setPayload(mass, cog)
            logger.info("Payload set to %.2f kg, CoG=%s", mass, cog)
        except Exception as e:
            raise MotionError(f"Failed to set payload: {e}")

    # ------------------------------------------------------------------
    # Motion guard helpers
    # ------------------------------------------------------------------

    def _disable_freedrive_guard(self) -> None:
        """Disable freedrive if active before motion.

        Freedrive and scripted motion conflict — if freedrive is on,
        disable it first and warn the user.
        """
        if self._motion.is_freedrive_active:
            logger.warning("Freedrive was active, disabling before motion")
            self._motion.disable_freedrive()

    # ------------------------------------------------------------------
    # Point lookup helpers
    # ------------------------------------------------------------------

    def _lookup_point(self, target: str | list[float]) -> Point:
        """Resolve a target (name or pose) to a Point.

        Args:
            target: A saved point name (str) or a raw pose list
                [x, y, z, rx, ry, rz].

        Returns:
            Point object with pose.
        """
        if _is_pose(target):
            return Point.from_pose(list(target))
        points = self._require_points()
        try:
            return points[target]
        except KeyError:
            raise PointError(
                f"Point '{target}' not found. "
                f"Available: {points.list()}"
            ) from None

    @staticmethod
    def _serialize_point(point: Point) -> dict:
        """Convert a Point to a serializable dict."""
        return {"pose": point.pose}

    # ------------------------------------------------------------------
    # Motion
    # ------------------------------------------------------------------

    def get_pose(
        self,
        target: str | list[float],
        *,
        offset: list[float] | None = None,
        frame: MoveFrame | None = None,
    ) -> list[float]:
        """Resolve a saved point or raw pose to a TCP pose.

        Like ``move_to`` but returns the pose instead of moving.
        Useful for logging, comparisons, or custom motion logic.

        Args:
            target: A saved point name (str) or a raw TCP pose
                [x, y, z, rx, ry, rz].
            offset: Optional offset [dx, dy, dz, droll, dpitch, dyaw]
                applied to the target pose.
            frame: Coordinate frame for the offset. Falls back to the
                current ``move_frame`` property (BASE or TOOL).

        Returns:
            TCP pose as [x, y, z, rx, ry, rz].

        Raises:
            PointError: If the named point is not found or offset is invalid.

        Example:
            >>> pose = robot.get_pose("pick")
            >>> pose = robot.get_pose("pick", offset=[0, 0, 0.05, 0, 0, 0])
            >>> robot.move_to(pose)
        """
        point = self._lookup_point(target)

        if offset is not None:
            if len(offset) != 6:
                raise PointError(
                    f"Offset must have 6 values [dx, dy, dz, droll, dpitch, dyaw], "
                    f"got {len(offset)}."
                )
            point = point.with_offset(offset, frame=frame or self._move_frame)

        return list(point.pose)

    def move_to(
        self,
        target: str | list[float],
        *,
        linear: bool = True,
        offset: list[float] | None = None,
        frame: MoveFrame | None = None,
        vel: float | None = None,
        acc: float | None = None,
    ) -> None:
        """Move to a saved point or raw pose.

        Args:
            target: A saved point name (str) or a raw TCP pose
                [x, y, z, rx, ry, rz].
            linear: If True (default), use Cartesian linear move (moveL).
                If False, use joint-space move (moveJ).
            offset: Optional offset [dx, dy, dz, droll, dpitch, dyaw]
                applied to the target pose before moving.
            frame: Coordinate frame for the offset. Falls back to the
                current ``move_frame`` property (BASE or TOOL).
            vel: Velocity override. Falls back to default_vel.
            acc: Acceleration override. Falls back to default_acc.

        Raises:
            MotionError: If the move fails or IK has no solution.
            PointError: If the named point is not found or offset is invalid.

        Example:
            >>> robot.move_to("home")
            >>> robot.move_to("pick", linear=False)
            >>> robot.move_to("place", offset=[0, 0, 0.05, 0, 0, 0])
            >>> robot.move_to("place", offset=[0, 0, 0.05], frame=MoveFrame.TOOL)
            >>> robot.move_to([0.5, 0, 0.3, 0, 0, 0])  # raw pose
        """
        self._check_connection()
        self._disable_freedrive_guard()

        point = self._lookup_point(target)

        # Apply offset if provided
        if offset is not None:
            if len(offset) != 6:
                raise PointError(
                    f"Offset must have 6 values [dx, dy, dz, droll, dpitch, dyaw], "
                    f"got {len(offset)}."
                )
            point = point.with_offset(offset, frame=frame or self._move_frame)

        pose = list(point.pose)

        vel = vel if vel is not None else self._default_vel
        acc = acc if acc is not None else self._default_acc

        try:
            if linear:
                self._motion.movel(pose, vel=vel, acc=acc)
            else:
                joints = self.inverse_kinematics(pose)
                self._motion.movej(joints, vel=vel, acc=acc)
        except MotionError:
            raise
        except Exception as e:
            target_label = (
                f"'{target}'" if isinstance(target, str) else str(target[:3])
            )
            raise MotionError(f"Move to {target_label} failed: {e}")

    def move_relative(
        self,
        delta: list[float],
        *,
        linear: bool = True,
        frame: MoveFrame | None = None,
        vel: float | None = None,
        acc: float | None = None,
    ) -> None:
        """Relative Cartesian move from the current position.

        Reads the current TCP pose, applies the delta in the given
        coordinate frame, and moves to the resulting pose.

        Args:
            delta: [dx, dy, dz, droll, dpitch, dyaw] in meters/radians.
            linear: If True (default), use Cartesian linear move.
                If False, solve IK and use joint-space move.
            frame: Coordinate frame for the delta. Falls back to the
                current ``move_frame`` property (BASE or TOOL).
            vel: Velocity override. Falls back to default_vel.
            acc: Acceleration override. Falls back to default_acc.

        Raises:
            MotionError: If the move fails.

        Example:
            >>> robot.move_relative([0, 0.01, 0, 0, 0, 0])  # 1cm along Y
            >>> robot.move_relative([0, 0, 0.05], frame=MoveFrame.TOOL)
        """
        self._check_connection()
        self._disable_freedrive_guard()

        if len(delta) != 6:
            raise MotionError(
                f"Relative move requires 6 values [dx,dy,dz,droll,dpitch,dyaw], "
                f"got {len(delta)}."
            )

        vel = vel if vel is not None else self._default_vel
        acc = acc if acc is not None else self._default_acc
        effective_frame = frame or self._move_frame

        try:
            current = list(self._rtde_r.getActualTCPPose())
            target = transform_pose_delta(current, delta, effective_frame)

            if linear:
                self._motion.movel(target, vel=vel, acc=acc)
            else:
                joints = self.inverse_kinematics(target)
                self._motion.movej(joints, vel=vel, acc=acc)
        except MotionError:
            raise
        except Exception as e:
            raise MotionError(f"Relative move failed: {e}")

    def move_sequence(
        self,
        targets: list[str | list[float]],
        *,
        linear: bool = True,
        blend_radius: float = 0.0,
        vel: float | None = None,
        acc: float | None = None,
    ) -> None:
        """Move through a sequence of points with optional blending.

        Executes the full path as a single RTDE command using ur_rtde's
        Path API. When *blend_radius* is set (in meters), the robot
        rounds corners instead of stopping at each intermediate waypoint —
        the same blending you set on the UR teach pendant.

        The first and last points always use a blend radius of 0 so the
        robot stops cleanly at the start and end of the sequence.

        Args:
            targets: List of saved point names or raw poses
                [x, y, z, rx, ry, rz].
            linear: If True (default), use Cartesian linear moves (moveL).
                If False, use joint-space moves (moveJ).
            blend_radius: Blending radius in meters (default 0.0 = stop
                at each point). Typical values: 0.001-0.1 (1mm-100mm).
                Applied to intermediate points only.
            vel: Velocity override. Falls back to default_vel.
            acc: Acceleration override. Falls back to default_acc.

        Raises:
            MotionError: If the sequence fails or fewer than 2 targets.
            PointError: If a named point is not found.

        Example:
            >>> # Move through waypoints, stop at each
            >>> robot.move_sequence(["a", "b", "c"])
            >>> # Smooth path with 2cm corner blending
            >>> robot.move_sequence(["a", "b", "c"], blend_radius=0.02)
            >>> # Joint-space sequence with blending
            >>> robot.move_sequence(["a", "b", "c"], linear=False, blend_radius=0.05)
        """
        self._check_connection()
        self._disable_freedrive_guard()

        if len(targets) < 2:
            raise MotionError(
                f"move_sequence requires at least 2 targets, got {len(targets)}."
            )

        v = vel if vel is not None else self._default_vel
        a = acc if acc is not None else self._default_acc

        # Import here to avoid hard dependency at module level.
        from rtde_control import Path, PathEntry  # noqa: N812

        path = Path()
        move_type = PathEntry.MoveL if linear else PathEntry.MoveJ

        for i, target in enumerate(targets):
            point = self._lookup_point(target)
            # First and last points: no blending (stop cleanly).
            # Intermediate points: use the configured blend radius.
            r = blend_radius if (0 < i < len(targets) - 1) else 0.0
            entry_data = list(point.pose) + [v, a, r]
            path.add_entry(
                PathEntry(move_type, PathEntry.PositionTcpPose, entry_data)
            )
            label = (
                f"'{target}'" if isinstance(target, str) else str(target[:3])
            )
            logger.info(
                "move_sequence: %s (r=%.3f) (%d/%d)", label, r, i + 1, len(targets)
            )

        try:
            self._rtde_c.movePath(path, False)  # False = synchronous
        except Exception as e:
            raise MotionError(f"move_sequence failed: {e}")

    def move_until_contact(
        self,
        speed_vector: list[float],
        *,
        threshold: float = 5.0,
        acceleration: float = 0.1,
    ) -> None:
        """Move until contact is detected via TCP force sensing.

        Runs an interruptible control loop — press Ctrl+C to stop at any time.

        Args:
            speed_vector: 6-element speed vector
                ``[vx, vy, vz, vRoll, vPitch, dYaw]`` in m/s and rad/s.
            threshold: Force/torque delta (N or Nm) that triggers contact.
                Contact fires when any wrench component changes by more
                than this value from the baseline reading.
            acceleration: Acceleration limit passed to ``speedL()`` in m/s².

        Example:
            >>> # Move straight down until contact
            >>> robot.move_until_contact([0, 0, -0.02, 0, 0, 0])
            >>> # Higher threshold for heavier contact
            >>> robot.move_until_contact([0, 0, -0.02, 0, 0, 0], threshold=10.0)
        """
        self._check_connection()
        self._disable_freedrive_guard()
        self._motion.move_until_contact(
            speed_vector, threshold=threshold, acceleration=acceleration
        )

    def move_velocity(
        self,
        speed_vector: list[float],
        duration: float,
        acceleration: float = 0.1,
    ) -> None:
        """Move at a constant Cartesian velocity for a given duration.

        Args:
            speed_vector: ``[vx, vy, vz, vRoll, vPitch, dYaw]`` in m/s.
            duration: How long to move in seconds.
            acceleration: Acceleration limit in m/s².

        Example:
            >>> # Move down at 20 mm/s for 1 second
            >>> robot.move_velocity([0, 0, -0.02, 0, 0, 0], duration=1.0)
        """
        self._check_connection()
        self._disable_freedrive_guard()
        self._motion.move_velocity(speed_vector, duration, acceleration=acceleration)

    def speed_stop(self) -> None:
        """Stop any ongoing speed motion (delta move)."""
        self._motion.speed_stop()

    def enable_freedrive(self, mode: FreedriveMode = FreedriveMode.ALL) -> None:
        """Enable freedrive mode.

        Args:
            mode: Which axes to allow manual movement on.
        """
        self._check_connection()
        self._motion.enable_freedrive(mode)

    def disable_freedrive(self) -> None:
        """Disable freedrive mode."""
        self._motion.disable_freedrive()

    @property
    def is_freedrive_active(self) -> bool:
        """Return whether freedrive is currently active."""
        return self._motion.is_freedrive_active

    def set_speed_slider(self, factor: float) -> None:
        """Set the speed slider factor (0.0–1.0)."""
        self._motion.set_speed_slider(factor)

    def get_speed_slider(self) -> float:
        """Get the current speed slider setting (0.0–1.0)."""
        return self._telemetry.get_speed_slider()

    # ------------------------------------------------------------------
    # Kinematics
    # ------------------------------------------------------------------

    def inverse_kinematics(self, pose: list[float], seed: list[float] | None = None) -> list[float]:
        """Solve inverse kinematics using the robot controller.

        Returns the joint angles for the given Cartesian pose. Uses the
        robot's own IK solver (via RTDE), so it works for any UR model
        with calibrated kinematics.

        Args:
            pose: TCP pose [x, y, z, rx, ry, rz].
            seed: Optional joint configuration to find the closest
                solution. If not provided, uses the robot's current
                joint positions.

        Returns:
            Joint angles [j0, j1, j2, j3, j4, j5] in radians.

        Raises:
            MotionError: If the pose is unreachable (no IK solution).

        Example:
            >>> joints = robot.inverse_kinematics([0.3, 0, 0.1, 0, 0, 0])
        """
        self._check_connection()
        qnear = seed if seed is not None else []
        try:
            if not self._rtde_c.getInverseKinematicsHasSolution(pose, qnear):
                raise MotionError(f"No IK solution for pose {pose}")
            return self._rtde_c.getInverseKinematics(pose, qnear)
        except MotionError:
            raise
        except Exception as e:
            raise MotionError(f"Inverse kinematics failed for pose {pose}: {e}")

    # ------------------------------------------------------------------
    # Telemetry
    # ------------------------------------------------------------------

    def current_point(self) -> dict:
        """Get the robot's current pose and joints.

        Convenience method combining ``get_tcp_pose()`` and
        ``get_joint_positions()`` into a single call.

        Returns:
            Dict with ``pose`` [x, y, z, rx, ry, rz] and
            ``joints`` [j0..j5].

        Example:
            >>> pos = robot.current_point()
            >>> print(pos["pose"])
        """
        return {
            "pose": self._telemetry.get_tcp_pose(),
            "joints": self._telemetry.get_joint_positions(),
        }

    def get_tcp_pose(self) -> list[float]:
        """Get the current TCP pose.

        Returns:
            [x, y, z, rx, ry, rz] in meters/radians.
        """
        return self._telemetry.get_tcp_pose()

    def get_joint_positions(self) -> list[float]:
        """Get the current joint positions.

        Returns:
            [j0, j1, j2, j3, j4, j5] in radians.
        """
        return self._telemetry.get_joint_positions()

    def get_tcp_force(self) -> list[float]:
        """Get the current force/torque at the TCP.

        Returns:
            [fx, fy, fz, mx, my, mz] in N/Nm.
        """
        return self._telemetry.get_tcp_force()

    def get_robot_mode(self) -> str:
        """Get the current robot mode string."""
        return self._telemetry.get_robot_mode()

    def get_speed_scaling(self) -> float:
        """Get the current speed scaling factor (0.0–1.0).

        Returns the trajectory limiter speed scaling — what fraction
        of the programmed speed the robot is actually running at.
        """
        return self._telemetry.get_speed_scaling()

    def get_payload(self) -> float:
        """Get the currently configured payload mass (kg)."""
        return self._telemetry.get_payload()

    def is_protective_stopped(self) -> bool:
        """Check if the robot is in protective stop."""
        return self._telemetry.is_protective_stopped()

    def is_emergency_stopped(self) -> bool:
        """Check if the robot is in emergency stop."""
        return self._telemetry.is_emergency_stopped()

    # ------------------------------------------------------------------
    # Point management
    # ------------------------------------------------------------------

    def save_point(self, name: str) -> Point:
        """Save the current robot position as a named point.

        Stores the TCP pose from getActualTCPPose(). The UR controller
        interprets the stored pose in whatever TCP frame is active at
        playback time, making points tool-agnostic by design.

        Overwrites if a point with the same name already exists.

        Args:
            name: Name for the saved point.

        Returns:
            The saved Point object.

        Raises:
            PointError: If points database is not set or saving fails.
        """
        points = self._require_points()
        pose = self._telemetry.get_tcp_pose()
        point = Point(name=name, pose=pose)
        points.save(point)
        logger.info("Saved point '%s'", name)
        return point

    def rename_point(self, old_name: str, new_name: str) -> None:
        """Rename a saved point.

        Args:
            old_name: Current name of the point.
            new_name: New name for the point.

        Raises:
            KeyError: If the point does not exist.
            PointError: If points database is not set.
        """
        points = self._require_points()
        points.rename(old_name, new_name)
        logger.info("Renamed point '%s' -> '%s'", old_name, new_name)

    def delete_point(self, name: str) -> None:
        """Delete a saved point.

        Args:
            name: Name of the point to delete.

        Raises:
            KeyError: If the point does not exist.
            PointError: If points database is not set.
        """
        points = self._require_points()
        points.delete(name)
        logger.info("Deleted point '%s'", name)

    def point_names(self) -> list[str]:
        """List all saved point names (sorted alphabetically).

        Returns:
            List of point name strings.  Returns an empty list if no
            points database is configured.
        """
        if self._points is None:
            return []
        return self._points.list()

    def export_points(self, path: str | Path) -> None:
        """Export all saved points to a JSON file.

        Args:
            path: Output file path (will be overwritten).

        Raises:
            PointError: If points database is not set.
        """
        points = self._require_points()
        points.export_json(path)
        logger.info("Exported points to %s", path)

    def import_points(self, path: str | Path) -> None:
        """Import saved points from a JSON file.

        Overwrites existing points with the same name.

        Args:
            path: Input JSON file path (exported by ``export_points``).

        Raises:
            PointError: If points database is not set or file format is invalid.
        """
        points = self._require_points()
        points.import_json(path)
        logger.info("Imported points from %s", path)

    # ------------------------------------------------------------------
    # I/O (delegated to IO)
    # ------------------------------------------------------------------

    def set_digital_output(self, pin: int, value: bool) -> None:
        """Set a digital output pin.

        Args:
            pin: Pin index (0-15). Pins 0-7 standard, 8-15 configurable.
            value: True for high, False for low.
        """
        self._io.set_digital_output(pin, value)

    def set_digital_outputs(
        self, values: Union[bool, dict[int, bool]]
    ) -> None:
        """Set multiple digital outputs at once.

        Pass a dict of ``{pin: value}`` pairs, or a single bool
        to set all pins 0-15 to the same value.

        Args:
            values: Dict mapping pin numbers to bool values,
                or a single bool to apply to all pins.

        Example:
            >>> robot.set_digital_outputs({0: True, 1: False, 8: True})
            >>> robot.set_digital_outputs(False)
        """
        self._io.set_digital_outputs(values)

    def get_digital_output(self, pin: int) -> bool:
        """Get the state of a digital output.

        Args:
            pin: Pin index (0-17). Pins 0-7 standard, 8-15 configurable,
                16-17 tool.

        Returns:
            True if high.
        """
        return self._io.get_digital_output(pin)

    def get_digital_input(self, pin: int) -> bool:
        """Get the state of a digital input.

        Args:
            pin: Pin index (0-17). Pins 0-7 standard, 8-15 configurable,
                16-17 tool.

        Returns:
            True if high.
        """
        return self._io.get_digital_input(pin)

    def wait_for_input(
        self,
        pin: int,
        value: bool = True,
        *,
        timeout: float = 10.0,
    ) -> bool:
        """Block until a digital input reaches the desired value.

        Args:
            pin: Digital input pin index (0-17).
            value: Desired value (True for high, False for low).
            timeout: Maximum wait time in seconds (default 10.0).

        Returns:
            True if the input reached the desired value, False if timed out.

        Example:
            >>> if not robot.wait_for_input(0, True, timeout=5.0):
            ...     raise TimeoutError("Limit switch not triggered")
        """
        return self._io.wait_for_input(pin, value, timeout=timeout)

    def get_tool_input(self, pin: int) -> bool:
        """Get the state of a tool digital input (pin 0-1).

        Tool inputs correspond to pins 16-17 on the robot's I/O board.
        """
        return self._io.get_tool_input(pin)

    def get_tool_output(self, pin: int) -> bool:
        """Get the state of a tool digital output (pin 0-1).

        Tool outputs correspond to pins 16-17 on the robot's I/O board.
        """
        return self._io.get_tool_output(pin)

    def get_analog_input(self, pin: int) -> float:
        """Get the value of a standard analog input (pin 0-1).

        Returns volts or amperes depending on robot configuration.
        """
        return self._io.get_analog_input(pin)

    def get_analog_output(self, pin: int) -> float:
        """Get the value of a standard analog output (pin 0-1).

        Returns volts or amperes depending on robot configuration.
        """
        return self._io.get_analog_output(pin)

    # ------------------------------------------------------------------
    # Recovery
    # ------------------------------------------------------------------

    def _check_connection(self) -> None:
        """Verify RTDE connection is still alive before motion."""
        if self._connection_lost:
            raise ConnectionError(
                "RTDE connection was lost. The robot must be reinitialized. "
                "Create a new URRobot instance."
            )

    def reconnect_rtde(self) -> None:
        """Reconnect RTDE interfaces and reinitialize subsystems.

        Use this after a protective stop or fault to re-establish
        the RTDE connection without creating a new URRobot instance.

        Disconnects all existing RTDE interfaces, reuploads the
        control script, and rebuilds Motion, Telemetry, and IO.

        Raises:
            ConnectionError: If reconnection fails.
        """
        logger.info("Reconnecting RTDE...")

        # Disconnect existing interfaces
        try:
            if getattr(self, '_rtde_c', None) is not None:
                self._rtde_c.disconnect()
        except Exception:
            pass
        try:
            if getattr(self, '_rtde_r', None) is not None:
                self._rtde_r.disconnect()
        except Exception:
            pass
        try:
            if getattr(self, '_rtde_io', None) is not None:
                self._rtde_io.disconnect()
        except Exception:
            pass

        # Reconnect
        try:
            self._rtde_c, self._rtde_r, self._rtde_io = _connect_rtde(
                self._ip,
                frequency=self._rtde_frequency,
            )
        except ConnectionError:
            raise
        except Exception as e:
            raise ConnectionError(f"Failed to reconnect RTDE: {e}")

        # Reinitialize subsystems
        self._telemetry = Telemetry(self._rtde_r)
        self._io = IO(self._rtde_io, self._rtde_r)
        self._motion = Motion(
            self._rtde_c,
            self._rtde_r,
            self._rtde_io,
            default_vel=self._default_vel,
            default_acc=self._default_acc,
        )

        # Reconnect gripper if it was active
        if getattr(self, '_gripper', None) is not None:
            try:
                self._gripper._rtde_c = self._rtde_c
                self._gripper._rtde_r = self._rtde_r
                self._gripper._activated = False
            except Exception:
                pass

        self._connection_lost = False
        logger.info("RTDE reconnected successfully")

    def disconnect(self) -> None:
        """Close RTDE connections, Dashboard socket, and points database.

        Call this when done to release resources. Safe to call even
        if __init__ failed partway through.
        """
        try:
            getattr(self, '_motion', None) and self._motion.stop_script()
        except Exception:
            pass
        try:
            gripper = getattr(self, '_gripper', None)
            if gripper is not None and hasattr(gripper, 'disconnect'):
                gripper.disconnect()
        except Exception:
            pass
        try:
            rtde_c = getattr(self, '_rtde_c', None)
            if rtde_c is not None:
                rtde_c.disconnect()
        except Exception:
            pass
        try:
            rtde_r = getattr(self, '_rtde_r', None)
            if rtde_r is not None:
                rtde_r.disconnect()
        except Exception:
            pass
        try:
            rtde_io = getattr(self, '_rtde_io', None)
            if rtde_io is not None:
                rtde_io.disconnect()
        except Exception:
            pass
        if getattr(self, '_dashboard', None) is not None:
            try:
                self._dashboard.close()
            except Exception:
                pass
            self._dashboard = None
        try:
            getattr(self, '_points', None) and self._points._close()
        except Exception:
            pass
        logger.info("URRobot disconnected")

    def __del__(self) -> None:
        self.disconnect()
