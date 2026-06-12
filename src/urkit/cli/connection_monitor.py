"""Connection monitoring for the teach pendant CLI.

Runs a daemon thread that periodically checks the RTDE connection
and robot safety state. Sends SIGALRM to interrupt blocking RTDE
calls when a fault or connection drop is detected.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
from typing import TYPE_CHECKING

from urkit.exceptions import URKitConnectionError

if TYPE_CHECKING:
    from urkit.robot import URRobot

logger = logging.getLogger(__name__)


class ConnectionMonitor:
    """Background thread that monitors RTDE connection and robot state.

    Checks isConnected() on the RTDE interfaces and the robot's
    protective/emergency stop state. When a fault is detected, sends
    SIGALRM to the process to interrupt any blocking RTDE call.

    Args:
        robot: URRobot instance to monitor.
        interval: Seconds between checks (default 0.5).
        grace_period: Seconds to wait before the first check (default
            2.0). Prevents false triggers while the CLI is initializing.

    Example:
        >>> monitor = ConnectionMonitor(robot)
        >>> monitor.start()
        >>> signal.signal(signal.SIGALRM, monitor.alarm_handler)
        >>> try:
        ...     # main loop with blocking RTDE calls
        ... except URKitConnectionError as e:
        ...     print(f"Fault: {e}")
        >>> monitor.stop()
    """

    def __init__(
        self,
        robot: "URRobot",
        interval: float = 0.5,
        grace_period: float = 2.0,
    ) -> None:
        self._robot = robot
        self._interval = interval
        self._grace_period = grace_period
        self._stop_event = threading.Event()
        self._fault_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._reason: str | None = None

    def start(self) -> None:
        """Start the monitoring thread."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._fault_event.clear()
        self._reason = None
        self._thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="connection-monitor",
        )
        self._thread.start()
        logger.info("Connection monitor started (interval=%.1fs)", self._interval)

    def stop(self) -> None:
        """Stop the monitoring thread."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        self._thread = None
        logger.info("Connection monitor stopped")

    @property
    def is_alive(self) -> bool:
        """Return whether the monitoring thread is running."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def fault_detected(self) -> bool:
        """Return True if a fault has been detected by the monitor."""
        return self._fault_event.is_set()

    def alarm_handler(self, signum: int, frame: object) -> None:
        """Signal handler for SIGALRM. Raises URKitConnectionError.

        Install this as the SIGALRM handler before entering any
        blocking RTDE call:
            signal.signal(signal.SIGALRM, monitor.alarm_handler)
        """
        reason = self._reason or "RTDE connection lost"
        raise URKitConnectionError(
            f"Robot fault detected: {reason}. RTDE connection lost."
        )

    def _monitor_loop(self) -> None:
        """Main monitoring loop running in the daemon thread."""
        # Grace period — wait before the first check so the CLI has time
        # to draw the screen and set up terminal mode. Prevents SIGALRM
        # from interrupting a blocking call before the UI is ready.
        if self._grace_period > 0:
            logger.info("Monitor grace period: %.1fs", self._grace_period)
            if self._stop_event.wait(self._grace_period):
                return

        while not self._stop_event.wait(self._interval):
            try:
                # Check RTDE connection status
                rtde_c = self._robot.rtde_control
                if not rtde_c.isConnected():
                    self._trigger("RTDE control connection lost")
                    return

                # Check for protective stop
                if self._robot.is_protective_stopped():
                    self._trigger("Robot is in protective stop")
                    return

                # Check for emergency stop
                if self._robot.is_emergency_stopped():
                    self._trigger("Robot is in emergency stop")
                    return

            except URKitConnectionError:
                # Re-raise alarm-triggered errors
                raise
            except Exception as e:
                # Any exception reading state suggests connection issues
                logger.warning("Connection monitor error: %s", e)
                self._trigger(f"Robot connection fault: {e}")
                return

        logger.info("Connection monitor loop exited")

    def _trigger(self, reason: str) -> None:
        """Record fault reason and send SIGALRM to interrupt blocking calls."""
        self._reason = reason
        self._fault_event.set()
        logger.info("Fault detected: %s", reason)
        try:
            os.kill(os.getpid(), signal.SIGALRM)
        except OSError as e:
            logger.error("Failed to send SIGALRM: %s", e)
