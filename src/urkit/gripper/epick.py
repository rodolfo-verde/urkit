"""Robotiq EPick vacuum gripper backend via RTDE preamble-based scripting.

Controls the EPick vacuum gripper over the same Robotiq RS485 gripper
protocol as the 2F grippers (ACT/GTO/SET POS/SPE/FOR over the robot's
tool serial port), using the official Robotiq preamble.  The protocol
parameter meanings differ from the 2F grippers:

- POS (2F: finger position) is the EPick's maximum vacuum request:
  0 = maximum vacuum, 100 = no vacuum, 255 = active release (blow-off)
- SPE (2F: speed) is the grip timeout in 100 ms units
- FOR (2F: force) is the minimum vacuum request
- GTO=1 starts the grip (or release) sequence

The gripper reports state in the OBJ register:
  0 = unknown / vacuum below minimum for > 1 s,
  1 = object secured (min vacuum reached),
  2 = object secured (max vacuum reached), 3 = no object / object lost.
A grip timeout sets FLT = 0x6.

Grip mode
---------

The EPick runs in advanced mode (rMOD=1), per Robotiq's URCap and the
EPick manual: in automatic mode (rMOD=0) the gripper sets the object
flag from a short, "seemingly constant" vacuum level, which produces
false positives with no object on the cup.  In advanced mode the pump
reaches the max level, stops, and the vacuum decays back to the min
level (the object flag toggles between gOBJ=0b10 and gOBJ=0b01 on
every cycle).  Measured on the robot with no object on the cup, the
pump still reaches max (OBJ=2) but the vacuum crashes and OBJ=1 never
occurs (0 hits over a 6 s window).  A grip success is therefore
SECURE_HITS (2) OBJ=1 (secured-to-min) reads anywhere in the wait
window.

With a max vacuum of 100% the gripper runs continuously and OBJ=2 is
never reachable; max vacuum < 100% (default 60, the Robotiq URCap
default) is the reliable production configuration.

Result reporting
----------------

Grip and release run as a single URScript that waits on the robot side
for the gripper's response.  The result is encoded in the call
duration, because output integer registers written by custom scripts
are not observable through the RTDE receive stream on this firmware:

- every script ends with a fixed tail sleep, so an executed call always
  takes at least ~1 s while a non-executed call returns in < 0.3 s;
- a failed wait (grip timeout / object not released) adds a 1.5 s
  marker sleep before the tail, so a failed call takes ~1.5 s longer
  than a successful one at the same timeout.

Stale-return protection
-----------------------

The ur_rtde custom script channel can return instantly without
executing the script (stale DONE marker in the control script state).
Every call is timed: if it returns faster than the tail sleep can
possibly take, the marker is re-primed (a read-only RTDE command ends
with a NO_CMD cycle that settles the control script to READY) and the
script is retried, up to MAX_ATTEMPTS times.

Hang protection
---------------

URScript has no exception handling: if a script faults on the robot
(e.g. no RS485 response), the DONE marker is never written and the
ur_rtde call blocks for its full 600 s timeout.  Every call therefore
runs in a watchdog thread with a deadline of expected max duration
plus a margin; exceeding it raises instead of hanging.

Semantics (inverted relative to the 2F position mapping):

- ``open()``  = release (vacuum off, wait for the object to drop)
- ``close()`` = grip (vacuum on, wait for the object to be detected;
  raises ``GripperError`` on grip timeout)
- ``set_position_percent(p)`` = vacuum level (0 = release, 100 = full)
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from urkit.exceptions import GripperError
from urkit.gripper.base import Gripper
from urkit.gripper.robotiq_preamble import ROBOTIQ_PREAMBLE

if TYPE_CHECKING:
    from rtde_control import RTDEControlInterface
    from rtde_receive import RTDEReceiveInterface

logger = logging.getLogger(__name__)

# Fixed sleep appended to every script. An executed call therefore
# always takes at least BASE_OVERHEAD + TAIL + cleanup, while a stale
# (non executed) call returns in well under STALE_THRESHOLD (the
# stale path pays the ~0.6 s control-script re-upload cost but none of
# the script work). Measured on the e-Series: stale <= ~0.9 s, executed
# >= ~2.0 s.
TAIL_SLEEP_S = 1.5
STALE_THRESHOLD_S = 1.5
# Extra on-robot sleep on a failed wait (grip timeout / release
# timeout). Sized so the failure band clears the success band for any
# timeout: success <= BASE_MAX + timeout + TAIL + 0.5, failure >=
# BASE_MIN + timeout + TAIL + FAIL_MARKER + 0.1.
FAIL_MARKER_S = 2.5
# Extra on-robot sleep for a positive probe result (object detected).
# The probe has no wait loop, so the result bands are:
# not detected: base + TAIL + cleanup      (<= ~3.0 s)
# detected:     base + PROBE_MARKER + TAIL + cleanup (>= ~3.8 s)
PROBE_MARKER_S = 2.0
# Midpoint of the two probe bands above.
PROBE_THRESHOLD_S = 3.4
# Empirical overhead of preamble + RS485 exchanges before the wait
# loop starts (measured ~0.2-1.0 s on the e-Series; the preamble's
# local socket handshake is fast when the gripper is connected).
BASE_OVERHEAD_S = 1.0
# Decode threshold offset: success exits early once secured, worst
# case just before the window ends: success <= BASE_MAX + timeout +
# TAIL + 0.5 (T + 3.0). Failure runs the full window plus the marker:
# failure >= BASE_MIN + timeout + TAIL + FAIL_MARKER + 0.1 (T + 4.3).
# T + 3.65 sits mid-gap.
DECODE_MARGIN_S = 1.15
# Retry/prime behavior for stale returns.
MAX_ATTEMPTS = 4
PRIME_SETTLE_S = 0.5
WATCHDOG_MARGIN_S = 10.0
# Release wait: how long to wait for the object to come off.
RELEASE_WAIT_S = 3.0
POLL_S = 0.1
# Cumulative OBJ=1 (secured-to-min) reads required for a grip to
# count as success. One per pump cycle for a sealed object; measured
# zero over a 6 s air window, so two hits anywhere in the window is
# unambiguous.
SECURE_HITS = 2

# URScript helpers appended after the Robotiq preamble.  They mirror
# the vacuum functions from Robotiq's official URCap (built on the
# same preamble primitives).
EPICK_HELPERS: str = "\n".join([
    "# OBJ: 1 or 2 = object secured (gripped)",
    "def epick_obj_detected(sock):",
    "    gOBJ = rq_get_var(OBJ, 1, sock)",
    "    if (gOBJ[0] == 1):",
    "        if (gOBJ[1] == 49 or gOBJ[1] == 50):",
    "            return True",
    "        end",
    "    end",
    "    return False",
    "end",
    "",
    "# OBJ == 1 = secured to min vacuum (decay phase, pump stopped).",
    "# Only occurs while the vacuum is actually held - never in the air.",
    "def epick_obj_min(sock):",
    "    gOBJ = rq_get_var(OBJ, 1, sock)",
    "    if (gOBJ[0] == 1):",
    "        if (gOBJ[1] == 49):",
    "            return True",
    "        end",
    "    end",
    "    return False",
    "end",
    "",
    "# FLT 0x6 = grip timeout (no object detected)",
    "def epick_grip_timeout(sock):",
    "    gFLT = rq_get_var(FLT, 2, sock)",
    "    if (gFLT[0] == 2 and gFLT[1] == 48):",
    "        if (gFLT[2] == 54):",
    "            return True",
    "        end",
    "    end",
    "    return False",
    "end",
    "",
    "# Clear a fault / activate if needed (Robotiq URCap sequence)",
    "def epick_reset_and_activate(sock):",
    "    gFLT = rq_get_var(FLT, 2, sock)",
    "    if (not is_FLT_no_fault(gFLT) or not rq_is_gripper_activated(sock)):",
    "        rq_set_var(GTO, 0, sock)",
    "        rq_set_var(ACT, 1, sock)",
    "    end",
    "end",
    "",
    "# SET POS/SPE/FOR with ack retry (Robotiq URCap sequence)",
    "def epick_set_params(pressure, timeout, minimum, sock):",
    "    enter_critical",
    "    rq_send_pos_spd_for(pressure, timeout, minimum, sock)",
    "    ack = socket_read_byte_list(3, sock)",
    "    exit_critical",
    "    sync()",
    "    while (is_not_ack(ack)):",
    "        enter_critical",
    "        rq_send_pos_spd_for(pressure, timeout, minimum, sock)",
    "        ack = socket_read_byte_list(3, sock)",
    "        exit_critical",
    "        sync()",
    "    end",
    "end",
    "",
])


class EpickGripper(Gripper):
    """Robotiq EPick vacuum gripper via RTDE preamble-based scripting.

    The EPick is a vacuum gripper: ``close()`` turns the vacuum on and
    waits for the object to be detected, ``open()`` releases (active
    blow-off) and waits for the object to drop.  There is no finger
    travel, so ``set_position_mm()`` raises.

    Grip parameters (all applied on the next grip):

    - ``max_vacuum`` (``set_max_vacuum``): maximum vacuum level, 20-100
      (default 60, the Robotiq URCap default; 100 = continuous
      vacuum mode, less reliable object detection)
    - ``min_vacuum`` (``set_min_vacuum``): minimum vacuum level at
      which the object counts as secured, 10 up to ``max_vacuum``
      (default 40, the Robotiq URCap default)
    - ``grip_timeout`` (``set_grip_timeout``): grip timeout 0-100 in
      100 ms units, mapped to 0-10000 ms (default 30 = 3 s, the
      Robotiq URCap default)

    Args:
        rtde_control: RTDEControlInterface (required).
        rtde_receive: RTDEReceiveInterface (required for factory
            compatibility; not used for result reading).
        max_vacuum: Maximum vacuum level 20-100 (default 60).
        min_vacuum: Minimum vacuum level 10 up to max_vacuum
            (default 40).
        grip_timeout: Grip timeout 0-100 in 100 ms units
            (default 30 = 3 s).
        max_mm: Accepted for factory compatibility, not used (a vacuum
            gripper has no finger travel).

    Raises:
        GripperError: If rtde_control is not provided, or max_vacuum /
            min_vacuum / grip_timeout are out of range.
    """

    def __init__(
        self,
        *,
        rtde_control: "RTDEControlInterface",
        rtde_receive: "RTDEReceiveInterface" | None = None,
        max_mm: int = 0,
        max_vacuum: int = 60,
        min_vacuum: int = 40,
        grip_timeout: int = 30,
        **kwargs: object,  # robot_ip passed by factory but not used
    ) -> None:
        if rtde_control is None:
            raise GripperError(
                "EpickGripper requires rtde_control (RTDEControlInterface)."
            )
        unknown = {k for k in kwargs if k != "robot_ip"}
        if unknown:
            cross = unknown & {"force", "speed"}
            if cross:
                raise GripperError(
                    f"{' and '.join(sorted(cross))} are 2F finger-gripper "
                    "parameters. The EPick uses max_vacuum, min_vacuum, "
                    "and grip_timeout instead."
                )
            raise GripperError(
                f"Unknown EPick gripper parameter(s): "
                f"{' and '.join(sorted(unknown))}. Valid: max_vacuum, "
                "min_vacuum, grip_timeout, max_mm."
            )
        if not 20 <= max_vacuum <= 100:
            raise GripperError(
                f"EPick max vacuum must be 20-100, got {max_vacuum}."
            )
        if not 10 <= min_vacuum <= max_vacuum:
            raise GripperError(
                f"EPick min vacuum must be 10-{max_vacuum}, got {min_vacuum}."
            )
        if not 0 <= grip_timeout <= 100:
            raise GripperError(
                f"EPick grip timeout must be 0-100, got {grip_timeout}."
            )

        self._rtde = rtde_control
        self._max_vacuum = max_vacuum
        self._min_vacuum = min_vacuum
        self._timeout_ms = int(grip_timeout * 100)
        self._activated = False

        logger.info(
            "EpickGripper initialized (max vacuum=%d%%, min vacuum=%d%%, "
            "timeout=%d ms)",
            self._max_vacuum, self._min_vacuum, self._timeout_ms,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_activated(self) -> None:
        """Raise an error if the gripper has not been activated."""
        if not self._activated:
            raise GripperError(
                "Gripper is not activated. Call activate() before "
                "using open(), close(), or is_object_detected()."
            )

    def _send_script(self, code: str, *, expected_max_s: float) -> float:
        """Send URScript and wait for it to execute, priming on stale returns.

        The code must already end with the tail sleep (see
        _script_tail).  Returns the call duration in seconds, which
        encodes the on-robot result (see the module docstring).

        Args:
            code: Complete URScript to execute.
            expected_max_s: Worst-case legitimate execution time
                (used for the watchdog deadline).

        Returns:
            Call duration in seconds (>= STALE_THRESHOLD_S).

        Raises:
            GripperError: If the script did not execute after
                MAX_ATTEMPTS primes, if the call exceeded the watchdog
                deadline (script faulted on the robot), or if the
                underlying send failed.
        """
        for attempt in range(1, MAX_ATTEMPTS + 1):
            box: dict = {}
            finished = threading.Event()

            def _run() -> None:
                try:
                    box["ok"] = self._rtde.sendCustomScriptFunction(
                        "_epick_cmd", code
                    )
                except Exception as e:  # noqa: BLE001 - surfaced by caller
                    box["err"] = e
                finally:
                    finished.set()

            th = threading.Thread(target=_run, daemon=True)
            deadline = expected_max_s + WATCHDOG_MARGIN_S
            t0 = time.monotonic()
            th.start()
            if not finished.wait(timeout=deadline):
                raise GripperError(
                    f"EPick script did not complete within {deadline:.0f}s "
                    "- the URScript likely faulted on the robot (e.g. no "
                    "RS485 response from the gripper). Reconnect the robot "
                    "and retry."
                )
            dt = time.monotonic() - t0
            if "err" in box:
                raise GripperError(
                    f"EPick script failed: {box['err']}"
                ) from box["err"]
            if not box.get("ok"):
                raise GripperError(
                    "sendCustomScriptFunction returned False - the RTDE "
                    "custom script channel is unavailable."
                )
            if dt >= STALE_THRESHOLD_S:
                return dt
            if attempt == MAX_ATTEMPTS:
                raise GripperError(
                    f"EPick command was not executed after {MAX_ATTEMPTS} "
                    "attempts (RTDE script channel unresponsive). "
                    "Reconnect the robot and retry."
                )
            logger.warning(
                "EPick script did not execute (dt=%.2fs), priming "
                "control script and retrying (attempt %d/%d)",
                dt, attempt, MAX_ATTEMPTS,
            )
            self._prime_control_script()
        raise GripperError("EPick command failed (unreachable).")

    def _prime_control_script(self) -> None:
        """Re-prime the ur_rtde control script marker to READY.

        A read-only RTDE command ends with a NO_CMD cycle that clears
        the pending command in the control script's input register,
        which settles its state marker back to READY (1) so the next
        custom script call is not treated as already-DONE.
        """
        try:
            self._rtde.getActualToolFlangePose()
        except Exception as e:
            logger.debug("Prime command failed: %s", e)
        time.sleep(PRIME_SETTLE_S)

    @staticmethod
    def _script_tail() -> str:
        """The fixed tail sleep appended to every EPick script."""
        return f"sleep({TAIL_SLEEP_S})\n"

    def _fail_marker(self) -> str:
        """The on-robot marker sleep for failed waits."""
        return f"    sleep({FAIL_MARKER_S})\n"

    # ------------------------------------------------------------------
    # Scripts
    # ------------------------------------------------------------------

    def _grip_script(self, vacuum_level: int, *, wait: bool) -> str:
        """Build the grip URScript (params + GTO + optional result wait).

        Args:
            vacuum_level: Maximum vacuum level 1-100.
            wait: If True, wait on the robot side for the object to be
                detected (or the grip timeout) and mark failure with an
                extra sleep.

        Returns:
            Complete URScript code string (ends with the tail sleep).
        """
        pressure = 100 - vacuum_level
        minimum = 100 - self._min_vacuum
        timeout_reg = self._timeout_ms // 100
        lines = [
            ROBOTIQ_PREAMBLE,
            EPICK_HELPERS,
            'epick_reset_and_activate("1")',
            f"epick_set_params({pressure}, {timeout_reg}, {minimum}, \"1\")",
            # Advanced mode (rMOD=1): constant production behavior,
            # pump cycles between max/min vacuum, OBJ stays 1/2 only
            # while the vacuum is actually held (no air blips).
            'rq_set_gripper_mode(1, "1")',
            'rq_set_GTO_and_wait(1, "1")',
        ]
        if wait:
            # Detection logic (advanced mode, per the EPick manual and
            # measured on the robot): with a sealed object the pump
            # cycles max -> stop -> decay, and OBJ=1 (secured to min)
            # recurs on every decay.  In the air the pump reaches max
            # (OBJ=2) but the vacuum crashes and OBJ=1 never occurs
            # (0 hits over a 6 s window).  Success = SECURE_HITS OBJ=1
            # reads anywhere in the window.
            max_polls = int(self._timeout_ms / (POLL_S * 1000)) + 10
            lines += [
                "epick_ok = 0",
                "epick_fault = 0",
                "epick_hits = 0",
                "epick_poll = 0",
                f"while (epick_ok == 0 and epick_fault == 0 "
                f"and epick_poll < {max_polls}):",
                '    if (epick_obj_min("1")):',
                "        epick_hits = epick_hits + 1",
                "    end",
                f"    if (epick_hits >= {SECURE_HITS}):",
                "        epick_ok = 1",
                "    end",
                '    if (epick_grip_timeout("1")):',
                "        epick_fault = 1",
                "    end",
                f"    sleep({POLL_S})",
                "    epick_poll = epick_poll + 1",
                "    sync()",
                "end",
                "if (epick_ok == 0):",
                self._fail_marker().rstrip("\n"),
                "end",
            ]
        lines.append(self._script_tail())
        return "\n".join(lines)

    def _release_script(self, *, wait: bool) -> str:
        """Build the release URScript (active blow-off + optional wait).

        Args:
            wait: If True, wait on the robot side until the gripper
                reports the object released and mark failure with an
                extra sleep.

        Returns:
            Complete URScript code string (ends with the tail sleep).
        """
        lines = [
            ROBOTIQ_PREAMBLE,
            EPICK_HELPERS,
            'epick_reset_and_activate("1")',
            'epick_set_params(255, 255, 0, "1")',
            'rq_set_gripper_mode(1, "1")',
            'rq_set_GTO_and_wait(1, "1")',
        ]
        if wait:
            max_polls = int(RELEASE_WAIT_S / POLL_S) + 10
            lines += [
                "epick_ok = 0",
                "epick_poll = 0",
                f"while (epick_ok == 0 and epick_poll < {max_polls}):",
                '    if (not epick_obj_detected("1")):',
                "        epick_ok = 1",
                "    end",
                f"    sleep({POLL_S})",
                "    epick_poll = epick_poll + 1",
                "    sync()",
                "end",
                "if (epick_ok == 0):",
                self._fail_marker().rstrip("\n"),
                "end",
            ]
        lines.append(self._script_tail())
        return "\n".join(lines)

    def _decode_wait(self, dt: float, *, timeout_s: float) -> bool:
        """Decode a wait-script result from the call duration.

        Returns:
            True if the on-robot wait succeeded, False if the failure
            marker sleep was executed.
        """
        return dt < BASE_OVERHEAD_S + timeout_s + TAIL_SLEEP_S + DECODE_MARGIN_S

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def activate(self, *, timeout: float = 20.0) -> None:
        """Activate the gripper.

        Checks the gripper's actual activation state on the robot using
        the preamble's ``rq_is_gripper_activated()``.  Only sends the
        activation command if the gripper is not already activated.
        Safe to call multiple times.

        Args:
            timeout: Maximum seconds to wait for activation (default
                20.0). The preamble's activation wait is unbounded, so
                this watchdog prevents hanging when no gripper responds
                on the RS485 bus.

        Raises:
            GripperError: If activation times out or fails.
        """
        if self._activated:
            return
        activation_script = (
            ROBOTIQ_PREAMBLE
            + "if (not rq_is_gripper_activated()):\n"
            + "    rq_activate_and_wait()\n"
            + "end\n"
            + self._script_tail()
        )
        # Expected max: the unbounded preamble wait cannot be bounded on
        # the robot side, so use a generous watchdog instead.
        self._send_script(activation_script, expected_max_s=20.0)
        self._activated = True
        logger.info("EPick gripper activated (checked robot state)")

    def is_activated(self) -> bool:
        """Check if the gripper has been activated."""
        return self._activated

    def deactivate(self) -> None:
        """Deactivate the gripper (send ACT=0).

        Sends the Robotiq deactivation command to power down the
        gripper.  Safe to call when not activated - becomes a no-op.
        Call activate() again to re-enable the gripper.
        """
        if not self._activated:
            return
        deact_script = (
            ROBOTIQ_PREAMBLE
            + 'rq_set_var(ACT, 0, "1")\n'
            + self._script_tail()
        )
        self._send_script(deact_script, expected_max_s=10.0)
        self._activated = False
        logger.info("EPick gripper deactivated")

    def open(self, *, wait: bool = True) -> None:
        """Release (vacuum off, active blow-off).

        Args:
            wait: If True, block until the gripper reports the object
                released (default True). If False, send the release
                command and return immediately.

        Raises:
            GripperError: If the gripper is not activated, or the
                release does not complete within the release wait.
        """
        self._require_activated()
        dt = self._send_script(
            self._release_script(wait=wait),
            expected_max_s=BASE_OVERHEAD_S + RELEASE_WAIT_S + FAIL_MARKER_S
            + TAIL_SLEEP_S,
        )
        if wait and not self._decode_wait(dt, timeout_s=RELEASE_WAIT_S):
            raise GripperError(
                "EPick release timed out - the gripper did not report "
                "the object released. Check the suction cup and "
                "workpiece."
            )
        logger.debug("EPick released (wait=%s, dt=%.2fs)", wait, dt)

    def close(self, *, wait: bool = True) -> None:
        """Grip (vacuum on).

        Waits for the gripper to detect the object. Raises if no object
        is detected within the grip timeout (see ``set_grip_timeout()``).

        Args:
            wait: If True, block until the gripper reports the object
                secured (default True). If False, send the grip command
                and return immediately.

        Raises:
            GripperError: If the gripper is not activated, or no object
                was detected within the grip timeout.
        """
        self._require_activated()
        dt = self._send_script(
            self._grip_script(self._max_vacuum, wait=wait),
            expected_max_s=BASE_OVERHEAD_S + self._timeout_ms / 1000
            + FAIL_MARKER_S + TAIL_SLEEP_S,
        )
        if wait and not self._decode_wait(dt, timeout_s=self._timeout_ms / 1000):
            raise GripperError(
                f"EPick grip timed out after {self._timeout_ms / 1000:.1f}s "
                "- no object detected. Check that the suction cup is "
                "seated on a flat, non-porous surface."
            )
        logger.debug("EPick gripped (wait=%s, dt=%.2fs)", wait, dt)

    def set_position_mm(self, mm: float) -> None:
        """Set the gripper position.

        Raises:
            GripperError: Always - the EPick is a vacuum gripper and
                has no finger travel.
        """
        raise GripperError(
            "EPick is a vacuum gripper and has no finger travel. "
            "Use open() or close() instead."
        )

    def set_position_percent(self, percent: int, *, wait: bool = True) -> None:
        """Grip at a specific vacuum level, or release at 0.

        For the EPick, percent is the vacuum level: 0 = release
        (vacuum off), 1-100 = grip at that vacuum level.

        Args:
            percent: Vacuum level 0-100.
            wait: If True, block until the gripper reports the grip or
                release result (default True).

        Raises:
            GripperError: If percent is out of range, the gripper is
                not activated, or the grip/release times out.
        """
        if not 0 <= percent <= 100:
            raise GripperError(f"EPick vacuum level must be 0-100, got {percent}.")
        self._require_activated()
        if percent == 0:
            self.open(wait=wait)
        else:
            level = max(1, percent)
            dt = self._send_script(
                self._grip_script(level, wait=wait),
                expected_max_s=BASE_OVERHEAD_S + self._timeout_ms / 1000
                + FAIL_MARKER_S + TAIL_SLEEP_S,
            )
            if wait and not self._decode_wait(
                dt, timeout_s=self._timeout_ms / 1000
            ):
                raise GripperError(
                    f"EPick grip timed out at {percent}% vacuum - no "
                    "object detected."
                )
            logger.debug(
                "EPick vacuum set to %d%% (wait=%s, dt=%.2fs)",
                percent, wait, dt,
            )

    def set_max_vacuum(self, max_vacuum: int) -> None:
        """Set the maximum vacuum level for subsequent grips.

        Args:
            max_vacuum: Max vacuum 20-100 (100 = full vacuum).
        """
        if not 20 <= max_vacuum <= 100:
            raise GripperError(
                f"EPick max vacuum must be 20-100, got {max_vacuum}."
            )
        if self._min_vacuum > max_vacuum:
            raise GripperError(
                f"EPick min vacuum ({self._min_vacuum}%) exceeds the new "
                f"max vacuum ({max_vacuum}%). Lower min vacuum first."
            )
        self._max_vacuum = max_vacuum
        logger.debug("EPick max vacuum set to %d%%", max_vacuum)

    def set_min_vacuum(self, min_vacuum: int) -> None:
        """Set the minimum vacuum level at which the object is secured.

        The grip succeeds once the vacuum reaches this level (the
        FOR register).  Must be at least 10 and at most the current
        max vacuum (``set_max_vacuum``).

        Args:
            min_vacuum: Min vacuum 10-100.

        Raises:
            GripperError: If min_vacuum is out of range or exceeds the
                current max vacuum.
        """
        if not 10 <= min_vacuum <= 100:
            raise GripperError(
                f"EPick min vacuum must be 10-100, got {min_vacuum}."
            )
        if min_vacuum > self._max_vacuum:
            raise GripperError(
                f"EPick min vacuum ({min_vacuum}%) exceeds max vacuum "
                f"({self._max_vacuum}%)."
            )
        self._min_vacuum = min_vacuum
        logger.debug("EPick min vacuum set to %d%%", min_vacuum)

    def set_grip_timeout(self, grip_timeout: int) -> None:
        """Set the grip timeout for subsequent grips.

        Args:
            grip_timeout: 0-100 in 100 ms units, mapped to 0-10000 ms
                (30 = 3 s).
        """
        if not 0 <= grip_timeout <= 100:
            raise GripperError(
                f"EPick grip timeout must be 0-100, got {grip_timeout}."
            )
        self._timeout_ms = int(grip_timeout * 100)
        logger.debug("EPick grip timeout set to %d ms", self._timeout_ms)

    def is_object_detected(self) -> bool:
        """Check whether the gripper currently reports a secured object.

        Useful after a grip to verify the hold, or during transport to
        detect an object drop.  The probe result is encoded in the call
        duration (a detected object adds a 1.5 s marker sleep).

        Returns:
            True if the gripper reports an object secured.

        Raises:
            GripperError: If the gripper is not activated, or the probe
                times out (gripper not responding on the RS485 bus).
        """
        self._require_activated()
        probe = (
            ROBOTIQ_PREAMBLE
            + "epick_probe = 0\n"
            + 'gOBJ = rq_get_var(OBJ, 1, "1")\n'
            + "if (gOBJ[0] == 1):\n"
            + "    if (gOBJ[1] == 49 or gOBJ[1] == 50):\n"
            + "        epick_probe = 1\n"
            + "    end\n"
            + "end\n"
            + "if (epick_probe == 1):\n"
            + f"    sleep({PROBE_MARKER_S})\n"
            + "end\n"
            + self._script_tail()
        )
        dt = self._send_script(probe, expected_max_s=15.0)
        return dt >= PROBE_THRESHOLD_S

    def disconnect(self) -> None:
        """Disconnect the gripper.

        Resets the activation flag. Call activate() again before
        using the gripper.
        """
        self._activated = False
        logger.debug("EPick gripper disconnected")

    def get_position_mm(self) -> float | None:
        """Return the last commanded position in mm.

        Returns:
            Always None - a vacuum gripper has no finger travel.
        """
        return None

    def max_travel_mm(self) -> float | None:
        """Return the maximum finger travel in mm.

        Returns:
            Always None - a vacuum gripper has no finger travel.
        """
        return None
