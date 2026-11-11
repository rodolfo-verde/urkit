"""Robotiq 2F gripper backend via RTDE preamble-based scripting.

Controls the gripper by sending URScript commands through RTDE's
``sendCustomScriptFunction()`` method, using the official Robotiq
preamble (``rq_*`` function library) for all communication.

The preamble is prepended to every command so the robot has the
function definitions and a live socket context.  This enables
synchronous motion: ``rq_move_and_wait`` polls the gripper's OBJ
register via ``socket_read_byte_list`` until the move completes or
contact is detected — all running on the robot side.

Each ``sendCustomScriptFunction`` call blocks until the full script
(preamble + function) finishes executing on the robot, making all
gripper operations synchronous by default.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from urkit.exceptions import GripperError
from urkit.gripper.base import Gripper
from urkit.gripper.robotiq_preamble import ROBOTIQ_PREAMBLE

if TYPE_CHECKING:
    from rtde_control import RTDEControlInterface
    from rtde_receive import RTDEReceiveInterface

logger = logging.getLogger(__name__)

# ur_rtde's sendCustomScriptFunction() blocks in the C++ layer until the
# robot-side script finishes (or a long internal timeout). If the script
# faults on the robot (e.g. no response from the gripper), that call can
# block for minutes, wedging the RTDE control channel. To keep a wedged
# call from blocking the caller indefinitely, every send runs in a daemon
# thread guarded by a watchdog: if the call does not return within the
# deadline, a GripperError is raised. The robot-side scripts are bounded
# (see robotiq_preamble.py), so a legitimate call always finishes well
# within the deadline and the watchdog only fires on a genuine fault.
# Watchdog deadlines (absolute). A legitimate call finishes well within
# its deadline; the watchdog only fires when the C++ call is wedged
# (script faulted on the robot). The activation deadline sits in the gap
# between a connected gripper (~4-6 s: fast preamble scan + 3-5 s
# activation) and no gripper (~8 s: the preamble's full bounded
# connection scan), so a missing gripper times out and raises.
ACTIVATE_DEADLINE_S = 7.0
MOVE_DEADLINE_S = 30.0  # a 2F move takes seconds; bounds a faulted gripper
DEACTIVATE_DEADLINE_S = 10.0


class RobotiqGripper(Gripper):
    """Robotiq 2F gripper via RTDE preamble-based scripting.

    Uses the official Robotiq preamble (``rq_*`` URScript functions)
    for all gripper communication.  Every command prepends the preamble
    so the robot has function definitions and a persistent socket
    context, enabling synchronous motion with built-in polling.

    Args:
        rtde_control: RTDEControlInterface (required).
        max_mm: Maximum finger travel in mm (default 50).
        force: Gripper force, 0-100 (default 100).
        speed: Gripper speed, 0-100 (default 100).

    Raises:
        GripperError: If rtde_control is not provided or force/speed
            are out of range.
    """

    def __init__(
        self,
        *,
        rtde_control: "RTDEControlInterface",
        rtde_receive: "RTDEReceiveInterface | None" = None,  # noqa: ARG002 - interface uniformity with EpickGripper
        max_mm: int = 50,
        force: int = 100,
        speed: int = 100,
        pin: int = 0,
        close_on_high: bool = True,
        **kwargs: object,  # robot_ip passed by factory but not used
    ) -> None:
        if rtde_control is None:
            raise GripperError(
                "RobotiqGripper requires rtde_control (RTDEControlInterface)."
            )
        unknown = {k for k in kwargs if k != "robot_ip"}
        if unknown:
            cross = unknown & {"max_vacuum", "min_vacuum", "grip_timeout"}
            if cross:
                raise GripperError(
                    f"{' and '.join(sorted(cross))} are EPick vacuum-gripper "
                    "parameters. The 2F uses force and speed instead."
                )
            raise GripperError(
                f"Unknown 2F gripper parameter(s): "
                f"{' and '.join(sorted(unknown))}. Valid: force, speed, "
                "max_mm, pin, close_on_high."
            )
        if not 0 <= force <= 100:
            raise GripperError(
                f"Robotiq gripper force must be 0-100, got {force}."
            )
        if not 0 <= speed <= 100:
            raise GripperError(
                f"Robotiq gripper speed must be 0-100, got {speed}."
            )

        self._rtde = rtde_control
        self._max_mm = max_mm
        self._force = force
        self._speed = speed
        self._activated = False
        self._activation_failed = False
        self._activation_running = False
        self._last_position_mm: float | None = None

        logger.info(
            "RobotiqGripper initialized (preamble, max_mm=%d)", max_mm
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_activated(self) -> None:
        """Raise an error if the gripper has not been activated."""
        if not self._activated:
            raise GripperError(
                "Gripper is not activated. Call activate() before "
                "using open(), close(), or set_position_mm()."
            )

    def _build_script(self, function_call: str) -> str:
        """Build a complete URScript: preamble + config + function call.

        The preamble defines all ``rq_*`` functions and initializes
        socket state.  Two config lines override the mm range for
        the current gripper model before the function executes.
        Force and speed are set before each operation.

        Args:
            function_call: A preamble function call (e.g. ``rq_open_and_wait()``).

        Returns:
            Complete URScript code string.
        """
        return (
            ROBOTIQ_PREAMBLE
            + "set_closed_mm(0.0, 1)\n"
            + f"set_open_mm({self._max_mm}.0, 1)\n"
            + f"rq_set_force({self._force}, 1)\n"
            + f"rq_set_speed({self._speed}, 1)\n"
            + f"{function_call}\n"
        )

    def _send_script(self, code: str, *, deadline_s: float) -> None:
        """Send URScript and wait for it to finish, bounded by a watchdog.

        The C++ ``sendCustomScriptFunction`` call blocks until the
        robot-side script finishes. If the script faults on the robot
        (e.g. no response from the gripper) that call can block for
        minutes, so it runs in a daemon thread guarded by a watchdog:
        if it does not return within the deadline, a GripperError is
        raised instead of blocking the caller.

        Args:
            code: Complete URScript to execute on the robot.
            deadline_s: Absolute watchdog deadline in seconds.

        Raises:
            GripperError: If the script did not complete within the
                deadline, or the underlying send failed.
        """
        box: dict = {}
        finished = threading.Event()

        def _run() -> None:
            try:
                box["ok"] = self._rtde.sendCustomScriptFunction(
                    "_gripper_cmd", code
                )
            except Exception as e:
                box["err"] = e
            finally:
                finished.set()

        th = threading.Thread(target=_run, daemon=True)
        th.start()
        if not finished.wait(timeout=deadline_s):
            raise GripperError(
                f"Gripper script did not complete within {deadline_s:.0f}s "
                "- the URScript likely faulted on the robot (e.g. no "
                "response from the gripper). Reconnect the robot and "
                "retry."
            )
        if "err" in box:
            raise GripperError(
                f"Gripper script failed: {box['err']}"
            ) from box["err"]
        if not box.get("ok"):
            raise GripperError(
                "sendCustomScriptFunction returned False - the RTDE "
                "custom script channel is unavailable."
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def activate(self, *, timeout: float | None = None) -> None:
        if timeout is None:
            timeout = ACTIVATE_DEADLINE_S
        """Activate the gripper.

        Checks the gripper's actual activation state on the robot using
        the preamble's ``rq_is_gripper_activated()``.  Only sends the
        activation command if the gripper is not already activated.

        The robot-side script is fully bounded (activation is gated on
        the preamble's connection scan; the activation wait is capped),
        so it always terminates on its own even with no gripper
        connected. This keeps the process clean on failure: the send
        thread has exited, the RTDE control register is released, and a
        retry with a new URRobot works immediately.

        A missing gripper is detected by the deadline: with no gripper
        the preamble runs its full bounded connection scan (~8 s), which
        exceeds the default deadline (~7 s), so activate() raises.
        With a connected gripper the script finishes in ~4-6 s, well
        within the deadline.

        Safe to call multiple times: skips activation if the gripper
        is already active on the robot.

        Args:
            timeout: Watchdog deadline in seconds (default
                ACTIVATE_DEADLINE_S). Set between the connected-gripper
                duration (~6 s) and the no-gripper duration (~8 s) so a
                missing gripper times out.

        Raises:
            GripperError: If the script does not complete within the
                deadline (e.g. no gripper connected), or an activation
                is already in progress.
        """
        if self._activated:
            return
        if self._activation_running:
            raise GripperError(
                "Gripper activation is already in progress. The script is "
                "bounded; wait for it to finish before retrying."
            )
        # Check activation state and activate if needed.
        # Activation is gated on gripper_1_connected (set by the
        # preamble's bounded connection scan): rq_activate() reaches
        # rq_set_var()'s unbounded ack-retry loop, which never returns
        # on a socket with no gripper behind it. The bounded
        # rq_activate_and_wait() covers a connected gripper that fails
        # to finish activation.
        activation_script = (
            ROBOTIQ_PREAMBLE
            + "set_closed_mm(0.0, 1)\n"
            + f"set_open_mm({self._max_mm}.0, 1)\n"
            + "if (not rq_is_gripper_activated()):\n"
            + "    if (gripper_1_connected):\n"
            + "        rq_activate_and_wait()\n"
            + "    end\n"
            + "end\n"
        )
        self._activation_running = True
        try:
            self._send_script(activation_script, deadline_s=timeout)
        except GripperError:
            self._activation_failed = True
            raise
        finally:
            self._activation_running = False
        self._activation_failed = False
        self._activated = True
        logger.info("Robotiq gripper activated")

    def is_activated(self) -> bool:
        """Check if the gripper has been activated."""
        return self._activated

    def _script_may_be_running(self) -> bool:
        """True if a gripper script may still be running on the robot.

        A failed or in-flight activation leaves a bounded gripper script
        finishing on the robot. ``URRobot.disconnect()`` uses this to skip
        ``stopScript()`` (the C++ call blocks while a gripper script runs).
        """
        return self._activation_failed or self._activation_running

    def deactivate(self) -> None:
        """Deactivate the gripper (send DEACT command).

        Sends the Robotiq DEACT command to power down the gripper.
        Safe to call when not activated — becomes a no-op.
        Call activate() again to re-enable the gripper.
        """
        if not self._activated:
            return
        deact_script = (
            'socket_open("127.0.0.1", 63352, "deact_sock")\n'
            "sync()\n"
            'socket_set_var("DEACT", 1, "deact_sock")\n'
            "sync()\n"
        )
        self._send_script(deact_script, deadline_s=DEACTIVATE_DEADLINE_S)
        self._activated = False
        logger.info("Robotiq gripper deactivated")

    def open(self, *, wait: bool = True) -> None:
        """Open the gripper (fully open).

        Args:
            wait: If True, block until the gripper reaches the open
                position (default True).  If False, return immediately.

        Raises:
            GripperError: If the gripper has not been activated.
        """
        self._require_activated()
        func = "rq_open_and_wait()" if wait else "rq_open()"
        self._send_script(self._build_script(func), deadline_s=MOVE_DEADLINE_S)
        self._last_position_mm = float(self._max_mm)
        logger.debug("Robotiq gripper opened (wait=%s)", wait)

    def close(self, *, wait: bool = True) -> None:
        """Close the gripper (fully closed).

        Args:
            wait: If True, block until the gripper reaches the closed
                position or detects contact (default True).  If False,
                return immediately.

        Raises:
            GripperError: If the gripper has not been activated.
        """
        self._require_activated()
        func = "rq_close_and_wait()" if wait else "rq_close()"
        self._send_script(self._build_script(func), deadline_s=MOVE_DEADLINE_S)
        self._last_position_mm = 0.0
        logger.debug("Robotiq gripper closed (wait=%s)", wait)

    def set_position_mm(self, mm: float, *, wait: bool = True) -> None:
        """Set the gripper to a specific opening in millimeters.

        Args:
            mm: Opening in mm (0 = fully closed, ``max_mm`` = fully open).
            wait: If True, block until the gripper reaches the target
                position or detects contact (default True).  If False,
                return immediately.

        Raises:
            GripperError: If the gripper has not been activated or
                position is out of range.
        """
        if not 0 <= mm <= self._max_mm:
            raise GripperError(
                f"Robotiq gripper position must be 0-{self._max_mm} mm, got {mm}."
            )
        self._require_activated()
        if wait:
            func = f"rq_move_and_wait_mm({mm})"
        else:
            func = f"rq_move_mm({mm})"
        self._send_script(self._build_script(func), deadline_s=MOVE_DEADLINE_S)
        self._last_position_mm = mm
        logger.debug("Robotiq gripper set to %.1f mm (wait=%s)", mm, wait)

    def set_position_percent(self, percent: int, *, wait: bool = True) -> None:
        """Set the gripper to a specific percentage opening.

        0 = fully open, 100 = fully closed. Delegates to the preamble's
        normalized functions (``rq_move_norm`` / ``rq_move_and_wait_norm``)
        which handle the 0-100 → 0-255 gripper protocol conversion.

        Args:
            percent: Percentage opening (0-100).
            wait: If True, block until the gripper reaches the target
                position (default True).

        Raises:
            GripperError: If percent is out of range or the gripper
                has not been activated.
        """
        if not 0 <= percent <= 100:
            raise GripperError(
                f"Robotiq gripper percent must be 0-100, got {percent}."
            )
        self._require_activated()
        func = (
            f"rq_move_and_wait_norm({percent})"
            if wait
            else f"rq_move_norm({percent})"
        )
        self._send_script(self._build_script(func), deadline_s=MOVE_DEADLINE_S)
        # Track last position in mm for consistency with get_position_mm()
        mm = self._max_mm * (1 - percent / 100.0)
        self._last_position_mm = mm
        logger.debug(
            "Robotiq gripper set to %d%% (%.1f mm) (wait=%s)",
            percent, mm, wait,
        )

    def set_force(self, force: int) -> None:
        """Set gripper force for subsequent movements.

        Args:
            force: Force 0-100.
        """
        if not 0 <= force <= 100:
            raise GripperError(
                f"Robotiq gripper force must be 0-100, got {force}."
            )
        self._force = force
        logger.debug("Robotiq gripper force set to %d", force)

    def set_speed(self, speed: int) -> None:
        """Set gripper speed for subsequent movements.

        Args:
            speed: Speed 0-100.
        """
        if not 0 <= speed <= 100:
            raise GripperError(
                f"Robotiq gripper speed must be 0-100, got {speed}."
            )
        self._speed = speed
        logger.debug("Robotiq gripper speed set to %d", speed)

    def disconnect(self) -> None:
        """Disconnect the gripper.

        Resets the activation flag. Call activate() again before
        using the gripper.
        """
        self._activated = False
        self._activation_failed = False
        self._last_position_mm = None
        logger.debug("Robotiq gripper disconnected")

    def get_position_mm(self) -> float | None:
        """Return the last commanded position in mm.

        Returns:
            Position in mm (0 = closed, max_mm = open), or None if
            no position has been set yet.
        """
        return self._last_position_mm

    def max_travel_mm(self) -> float:
        """Return the maximum finger travel in mm."""
        return float(self._max_mm)
