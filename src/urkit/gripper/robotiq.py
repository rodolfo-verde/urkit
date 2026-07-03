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

logger = logging.getLogger(__name__)


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
        max_mm: int = 50,
        force: int = 100,
        speed: int = 100,
        pin: int = 0,
        close_on_high: bool = True,
        **kwargs: object,  # rtde_receive, robot_ip passed by factory but not used
    ) -> None:
        if rtde_control is None:
            raise GripperError(
                "RobotiqGripper requires rtde_control (RTDEControlInterface)."
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
                "using open(), close(), or set_position()."
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

    def _send_script(self, code: str) -> None:
        """Send URScript code via sendCustomScriptFunction.

        Blocks until the script finishes executing on the robot.

        Args:
            code: URScript code to execute on the robot.

        Raises:
            GripperError: If the script fails to send.
        """
        try:
            ok = self._rtde.sendCustomScriptFunction("_gripper_cmd", code)
        except Exception as e:
            raise GripperError(f"Failed to send gripper script: {e}") from e
        if not ok:
            raise GripperError(
                "sendCustomScriptFunction returned False — "
                "RTDE custom script client may not be available."
            )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def activate(self, *, timeout: float = 5.0) -> None:
        """Activate the gripper and open it to a known safe state.

        Checks the gripper's actual activation state on the robot using
        the preamble's ``rq_is_gripper_activated()``.  Only sends the
        activation command if the gripper is not already activated.  If
        already activated, opens the gripper to a known safe state.

        Safe to call multiple times — skips activation if the gripper
        is already active on the robot.

        Args:
            timeout: Maximum seconds to wait for activation (default
                5.0). The Robotiq preamble blocks indefinitely if no
                gripper is connected, so this prevents hanging.

        Raises:
            GripperError: If activation fails or times out.
        """
        if self._activated:
            return
        # Check activation state and activate if needed.
        # rq_activate_and_wait() sends ACT then polls until the gripper
        # reports activated (~3-5s for internal initialization).
        activation_script = (
            ROBOTIQ_PREAMBLE
            + "set_closed_mm(0.0, 1)\n"
            + f"set_open_mm({self._max_mm}.0, 1)\n"
            + "if (not rq_is_gripper_activated()):\n"
            + "    rq_activate_and_wait()\n"
            + "end\n"
        )
        # Run in a thread with a timeout — the preamble blocks indefinitely
        # if no gripper is physically connected (2000-iteration loop).
        _ready = threading.Event()
        _err: Exception | None = None

        def _do_activate() -> None:
            nonlocal _err
            try:
                self._send_script(activation_script)
            except Exception as e:
                _err = e
            finally:
                _ready.set()

        threading.Thread(target=_do_activate, daemon=True).start()
        if not _ready.wait(timeout=timeout):
            raise GripperError(
                f"Gripper activation timed out after {timeout:.0f}s — "
                "check that the gripper is physically connected and powered."
            )
        if _err is not None:
            raise GripperError(f"Gripper activation failed: {_err}") from _err

        self._activated = True
        logger.info("Robotiq gripper activated (checked robot state)")

    def is_activated(self) -> bool:
        """Check if the gripper has been activated."""
        return self._activated

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
        self._send_script(deact_script)
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
        self._send_script(self._build_script(func))
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
        self._send_script(self._build_script(func))
        self._last_position_mm = 0.0
        logger.debug("Robotiq gripper closed (wait=%s)", wait)

    def set_position(self, mm: float, *, wait: bool = True) -> None:
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
        self._send_script(self._build_script(func))
        self._last_position_mm = mm
        logger.debug("Robotiq gripper set to %.1f mm (wait=%s)", mm, wait)

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
