"""Pre-connection validation for Universal Robots e-Series.

Performs ping, port checks, and remote mode verification.
Connects to RTDE interfaces using ur_rtde's default constructor,
which uploads its own control script (no Dashboard, .urp, or URCap
program needed). Raises typed exceptions with actionable messages.
"""

from __future__ import annotations

import logging
import socket
import time
from typing import TYPE_CHECKING, Tuple

from urkit.exceptions import URKitConnectionError as ConnectionError
from urkit.exceptions import RobotNotInRemoteModeError
from urkit.exceptions import RtdeRegisterConflictError

if TYPE_CHECKING:
    from rtde_control import RTDEControlInterface
    from rtde_io import RTDEIOInterface
    from rtde_receive import RTDEReceiveInterface

logger = logging.getLogger(__name__)

# Required ports and their purposes
_REQUIRED_PORTS: list[tuple[int, str]] = [
    (30004, "RTDE (data receive)"),
    (29999, "Dashboard"),
    (30001, "Primary interface"),
]

# RTDE port for control (also required)
_RTDE_CONTROL_PORT = 30003


def _ping(ip: str, timeout: float = 3.0) -> bool:
    """Ping the robot IP to verify basic network reachability.

    Uses a TCP connect to port 30001 (primary interface) as a
    lightweight ping since ICMP may be blocked on industrial networks.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((ip, 30001))
            return True
    except (socket.timeout, socket.error, OSError):
        return False


def _check_port(ip: str, port: int, timeout: float = 2.0) -> bool:
    """Check if a TCP port is open on the robot.

    Returns True if the port accepts a connection within timeout.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((ip, port))
            return True
    except (socket.timeout, socket.error, OSError):
        return False


def _check_all_ports(ip: str) -> dict[int, str]:
    """Check all required ports. Returns {port: status} dict."""
    results: dict[int, str] = {}
    for port, description in _REQUIRED_PORTS:
        results[port] = "open" if _check_port(ip, port) else "closed"

    # Also check RTDE control port
    control_open = _check_port(ip, _RTDE_CONTROL_PORT)
    results[_RTDE_CONTROL_PORT] = "open" if control_open else "closed"
    return results


def _check_remote_mode(ip: str, timeout: float = 5.0) -> bool:
    """Check if the robot is in remote control mode via Dashboard protocol.

    Sends 'is in remote control\\n' to port 29999 and parses the response.
    Returns True if remote control mode is active.

    Uses 'is in remote control' rather than 'robotmode' because robotmode
    only returns a string containing "remote control" when a remote program
    is actively executing. When the robot is idle (brakes released, no
    program running), robotmode returns "IDLE" — even though remote control
    is enabled. 'is in remote control' returns "True"/"False" regardless
    of whether a program is running.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((ip, 29999))

            # Read welcome banner
            s.recv(1024)

            # Query remote control status
            s.send(b"is in remote control\n")
            response = s.recv(1024).decode("utf-8").strip()

            # Response is "True" or "False"
            return response.lower() == "true"

    except (socket.timeout, socket.error, OSError):
        return False


def _validate_connection(ip: str, timeout: float = 5.0) -> dict[str, object]:
    """Validate that the robot is reachable and required ports are open.

    Performs:
    1. Ping check (TCP connect to port 30001)
    2. Required port checks (30004, 29999, 30001, 30003)

    Does not check remote mode — that is handled separately by callers.

    Args:
        ip: Robot IP address.
        timeout: Timeout in seconds for each check.

    Returns:
        Dict with validation results:
        {
            "ping_ok": bool,
            "ports": {port: "open"/"closed", ...},
            "ok": bool,
            "errors": list[str],
        }

    Raises:
        ConnectionError: If any validation step fails.
    """
    errors: list[str] = []

    # Step 1: Ping
    ping_ok = _ping(ip, timeout=timeout)
    if not ping_ok:
        errors.append(
            f"Robot at {ip} is not reachable. "
            f"Check network cable, IP address, and that the robot is powered on."
        )

    # Step 2: Port checks
    ports = _check_all_ports(ip)
    closed_ports = [p for p, status in ports.items() if status == "closed"]
    for port in closed_ports:
        desc = next((d for p, d in _REQUIRED_PORTS if p == port), "unknown service")
        errors.append(f"Port {port} ({desc}) is closed on {ip}")

    ok = ping_ok and len(closed_ports) == 0

    result = {
        "ping_ok": ping_ok,
        "ports": ports,
        "ok": ok,
        "errors": errors,
    }

    if errors:
        raise ConnectionError(
            f"Connection validation failed for {ip}:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    return result


def _connect_rtde(
    ip: str,
    *,
    frequency: float = 500.0,
    max_wait: float = 30.0,
) -> Tuple[
    "RTDEControlInterface",
    "RTDEReceiveInterface",
    "RTDEIOInterface",
]:
    """Connect to RTDE interfaces.

    Uses ur_rtde's default constructor which uploads its own control
    script to the robot's Secondary Interface (port 30002). No Dashboard
    commands, .urp file, or URCap program are needed.

    The user's only prerequisites are:
    - Remote Control enabled on the teach pendant
    - No conflicting fieldbus adapters (EtherNet/IP, PROFINET, MODBUS)

    Retries with a socket timeout so the constructor does not block
    indefinitely when the robot has just booted and the RTDE service
    is not yet ready.

    Args:
        ip: Robot IP address.
        frequency: RTDE communication frequency (default 500 Hz).
        max_wait: Maximum time (seconds) to spend retrying the RTDE
            connection (default 30s).

    Returns:
        Tuple of (RTDEControlInterface, RTDEReceiveInterface, RTDEIOInterface).

    Raises:
        ConnectionError: If ur_rtde is not installed or connection fails
            for an unhandled reason.
        RobotNotInRemoteModeError: If the robot is not in remote mode.
        RtdeRegisterConflictError: If RTDE registers are claimed by
            another protocol.
    """
    try:
        from rtde_control import RTDEControlInterface
        from rtde_io import RTDEIOInterface
        from rtde_receive import RTDEReceiveInterface
    except ImportError:
        raise ConnectionError(
            "ur_rtde package is not installed. "
            "Install it with: pip install ur_rtde"
        )

    logger.info(
        "Connecting to RTDE at %s (frequency=%sHz, max_wait=%ss)...",
        ip, frequency, max_wait,
    )

    start = time.time()
    attempt = 0

    while time.time() - start < max_wait:
        attempt += 1
        rtde_c = None
        rtde_r = None
        rtde_io = None

        try:
            rtde_c = RTDEControlInterface(ip, frequency=frequency)
            rtde_r = RTDEReceiveInterface(ip, frequency=frequency)
            rtde_io = RTDEIOInterface(ip)

            logger.info("RTDE connection established (attempt %d)", attempt)
            return rtde_c, rtde_r, rtde_io

        except (socket.timeout, socket.error, OSError) as e:
            # Clean up partially created interfaces on failure
            if rtde_io is not None:
                try:
                    rtde_io.disconnect()
                except Exception:
                    pass
            if rtde_r is not None:
                try:
                    rtde_r.disconnect()
                except Exception:
                    pass
            if rtde_c is not None:
                try:
                    rtde_c.disconnect()
                except Exception:
                    pass

            remaining = max_wait - (time.time() - start)
            if remaining <= 0:
                break

            logger.info(
                "RTDE connection attempt %d failed (%s), retrying in 1s (%.0fs remaining)...",
                attempt, e, remaining,
            )
            # Print progress every few attempts so the user doesn't think it's stuck
            if attempt % 3 == 0:
                print(
                    f"  Waiting for RTDE service... ({remaining:.0fs remaining})",
                    flush=True,
                )
            time.sleep(1)

        except RuntimeError as e:
            # ur_rtde raises RuntimeError for its own failures (e.g.,
            # "Failed to start control script"). Retry these — the robot
            # may still be booting or a program may occupy the interface.
            err_msg = str(e)

            if "remote control" in err_msg.lower() or "not in remote mode" in err_msg.lower():
                raise RobotNotInRemoteModeError(
                    f"Failed to connect to RTDE at {ip}. "
                    f"Please enable Remote Control: "
                    f"On the teach pendant, go to Settings → System → Remote Control → Enable. "
                    f"Then press the remote/local button to put the robot in remote mode."
                ) from e

            if "register" in err_msg.lower() and (
                "in use" in err_msg.lower() or "already" in err_msg.lower()
            ):
                raise RtdeRegisterConflictError(
                    f"RTDE registers are in use by another protocol at {ip}. "
                    f"On the teach pendant, go to Installation → Fieldbus and disable "
                    f"EtherNet/IP, PROFINET, and MODBUS. Save and restart."
                ) from e

            if "start control script" in err_msg.lower():
                raise ConnectionError(
                    f"Failed to start the RTDE control script on the robot at {ip}. "
                    f"The robot is missing the ExternalControl URCap program. "
                    f"Download external_control.urp from the ur_rtde repository "
                    f"(https://github.com/roboticsur/ur_rtde) and install it on the robot. "
                    f"Then press Play on the teach pendant to start the program."
                ) from e

            # Retryable RuntimeError (e.g., transient connection issues)
            remaining = max_wait - (time.time() - start)
            if remaining <= 0:
                raise ConnectionError(
                    f"Failed to connect to RTDE interfaces at {ip}: {e}"
                ) from e

            logger.info(
                "RTDE connection attempt %d failed (%s), retrying in 1s (%.0fs remaining)...",
                attempt, err_msg, remaining,
            )
            if attempt % 3 == 0:
                print(
                    f"  Waiting for RTDE service... ({remaining:.0fs remaining})",
                    flush=True,
                )
            time.sleep(1)

        except Exception as e:
            # Non-retryable errors
            err_msg = str(e)

            if "remote control" in err_msg.lower() or "not in remote mode" in err_msg.lower():
                raise RobotNotInRemoteModeError(
                    f"Failed to connect to RTDE at {ip}. "
                    f"Please enable Remote Control: "
                    f"On the teach pendant, go to Settings → System → Remote Control → Enable. "
                    f"Then press the remote/local button to put the robot in remote mode."
                ) from e

            if "register" in err_msg.lower() and (
                "in use" in err_msg.lower() or "already" in err_msg.lower()
            ):
                raise RtdeRegisterConflictError(
                    f"RTDE registers are in use by another protocol at {ip}. "
                    f"On the teach pendant, go to Installation → Fieldbus and disable "
                    f"EtherNet/IP, PROFINET, and MODBUS. Save and restart."
                ) from e

            raise ConnectionError(
                f"Failed to connect to RTDE interfaces at {ip}: {e}"
            ) from e

    raise ConnectionError(
        f"Failed to connect to RTDE at {ip} after {max_wait:.0fs} "
        f"({attempt} attempts). The robot may still be booting. "
        f"Wait a few seconds and try again."
    )


# Safety statuses that don't block normal operation
_SAFE_STATUSES = {"NORMAL", "REDUCED", "RECOVERY"}

# Safety statuses we can recover from via Dashboard
_RECOVERABLE_STATUSES = {"PROTECTIVE_STOP", "VIOLATION"}

# Safety statuses that require manual intervention on the teach pendant
_UNRECOVERABLE_STATUSES = {
	"FAULT",
	"SAFEGUARD_STOP",
	"SYSTEM_EMERGENCY_STOP",
	"ROBOT_EMERGENCY_STOP",
	"AUTOMATIC_MODE_SAFEGUARD_STOP",
	"SYSTEM_THREE_POSITION_ENABLING_STOP",
}


def _check_safety_status(ip: str, timeout: float = 5.0) -> str:
	"""Query the robot's current safety status via Dashboard.

	Returns the raw response string (e.g., "Safetystatus: NORMAL").
	"""
	s = _connect_dashboard(ip, timeout=timeout)

	try:
		response = _dashboard_command(s, "safetystatus", timeout=3.0)
		return response.strip()
	finally:
		s.close()


def _extract_safety_status(raw: str) -> str:
	"""Extract the status token from a 'Safetystatus: <status>' response.

	Handles multi-word statuses like 'SYSTEM_EMERGENCY_STOP'.
	Returns the raw upper-cased string if parsing fails.
	"""
	if ":" in raw:
		return raw.split(":", 1)[1].strip()
	return raw.strip()


def _try_recover_safety(ip: str, timeout: float = 30.0) -> tuple[bool, str]:
	"""Attempt to recover from a safety violation via Dashboard.

	Recovery actions by status:
	- PROTECTIVE_STOP → send `unlock protective stop`
	- VIOLATION → send `close safety popup` then `restart safety`
	  (robot returns to POWER_OFF after restart safety)
	- NORMAL / REDUCED / RECOVERY → no action needed
	- FAULT / SAFEGUARD_STOP / EMERGENCY_STOP → cannot recover remotely

	Args:
		ip: Robot IP address.
		timeout: Timeout for Dashboard connection.

	Returns:
		Tuple of (success, status).
		- success=True means the robot is ready to proceed.
		- success=False means manual intervention is required.
		- status is the current safety status string.

	Raises:
		ConnectionError: If Dashboard is unreachable.
	"""
	raw = _check_safety_status(ip, timeout=timeout)
	status = _extract_safety_status(raw).upper()

	logger.info("Robot safety status: %s", status)

	if status in _SAFE_STATUSES:
		logger.info("Safety status OK: %s", status)
		return True, status

	if status in _RECOVERABLE_STATUSES:
		try:
			s = _connect_dashboard(ip, timeout=timeout)
			try:
				if status == "PROTECTIVE_STOP":
					response = _dashboard_command(

						s, "unlock protective stop", timeout=10.0
					)
					logger.info("Unlock protective stop: %s", response)
					print("  Unlocking protective stop...", flush=True)
					# Wait for the protective stop to fully release
					time.sleep(2)

				elif status == "VIOLATION":
					# Close any safety popup first
					try:
						response = _dashboard_command(

							s, "close safety popup", timeout=5.0
						)
						logger.info("Close safety popup: %s", response)
						print("  Closing safety popup...", flush=True)
					except ConnectionError:
						logger.warning("Failed to close safety popup, continuing")

					# Restart the safety stack
					response = _dashboard_command(

						s, "restart safety", timeout=10.0
					)
					logger.info("Restart safety: %s", response)
					print("  Restarting safety stack...", flush=True)
					# After restart safety, the robot is in POWER_OFF.
					# The caller needs to power on and release brakes.
					time.sleep(2)

			finally:
				s.close()

			# Re-check status after recovery attempt
			try:
				raw = _check_safety_status(ip, timeout=timeout)
				status = _extract_safety_status(raw).upper()
				logger.info("Safety status after recovery: %s", status)
			except ConnectionError:
				pass

			return True, status

		except ConnectionError as e:
			logger.warning("Safety recovery failed: %s", e)
			return False, status

	# Unrecoverable — requires manual intervention
	return False, status


def _get_safety_help_message(status: str) -> str:
	"""Return a user-friendly help message for an unrecoverable safety status."""
	messages = {
		"FAULT": (
			"The robot is in a FAULT state (hardware fault or critical error).\n"
			"  This cannot be cleared remotely.\n"
			"  On the teach pendant:\n"
			"    1. Acknowledge the fault message\n"
			"    2. Fix the underlying issue\n"
			"    3. Press the reset button if needed\n"
			"    4. Then try again"
		),
		"SAFEGUARD_STOP": (
			"The robot is in a SAFEGUARD_STOP (safety circuit open).\n"
			"  Check the safety circuit (light curtains, e-stop chain, etc.).\n"
			"  Once the circuit is closed, the robot should recover automatically."
		),
		"SYSTEM_EMERGENCY_STOP": (
			"The robot is in a SYSTEM_EMERGENCY_STOP.\n"
			"  On the teach pendant:\n"
			"    1. Release the emergency stop button\n"
			"    2. Press the reset button\n"
			"    3. Then try again"
		),
		"ROBOT_EMERGENCY_STOP": (
			"The robot is in a ROBOT_EMERGENCY_STOP.\n"
			"  On the teach pendant:\n"
			"    1. Release the emergency stop button\n"
			"    2. Press the reset button\n"
			"    3. Then try again"
		),
		"AUTOMATIC_MODE_SAFEGUARD_STOP": (
			"The robot is in an AUTOMATIC_MODE_SAFEGUARD_STOP.\n"
			"  Check the automatic mode safety circuit.\n"
			"  Once resolved, the robot should recover."
		),
		"SYSTEM_THREE_POSITION_ENABLING_STOP": (
			"The robot requires the three-position enabling device.\n"
			"  Press and hold the enabling device on the teach pendant,\n"
			"  or clear the stop from the pendant."
		),
	}
	return messages.get(
		status,
		f"Safety status {status} requires manual intervention on the teach pendant."
	)


def _connect_dashboard(ip: str, timeout: float = 5.0) -> socket.socket:
    """Open a raw TCP socket to the Dashboard server.

    Args:
        ip: Robot IP address.
        timeout: Socket timeout in seconds.

    Returns:
        Connected socket object (caller is responsible for closing).

    Raises:
        ConnectionError: If Dashboard connection fails.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((ip, 29999))
        # Read welcome banner
        s.recv(1024)
        return s
    except (socket.timeout, socket.error, OSError) as e:
        raise ConnectionError(
            f"Dashboard server at {ip}:29999 is not reachable: {e}"
        )


def _dashboard_command(s: socket.socket, command: str, timeout: float = 5.0) -> str:
    """Send a command to the Dashboard server and return the response.

    Args:
        s: Connected Dashboard socket.
        command: Command string (e.g., "power on", "robotmode").
        timeout: Response timeout in seconds.

    Returns:
        Response string from the robot.

    Raises:
        ConnectionError: If the command times out or fails.
    """
    try:
        s.send(f"{command}\n".encode("utf-8"))
        response = s.recv(1024).decode("utf-8").strip()
        return response
    except socket.timeout:
        raise ConnectionError(
            f"Dashboard command '{command}' timed out on {s}"
        )
    except Exception as e:
        raise ConnectionError(
            f"Dashboard command '{command}' failed: {e}"
        )
