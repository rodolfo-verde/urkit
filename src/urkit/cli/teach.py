"""Interactive teach pendant CLI for Universal Robots e-Series.

A single terminal-based UI for manual robot control, point management,
and freedrive — matching the pattern from robot_mover's point_saver.cpp.

Usage:
    urkit 192.168.1.100                  # connect with IP
    urkit                                # reads robot_ip from config
    urkit -v 192.168.1.100               # verbose (debug boot commands)
"""

from __future__ import annotations

import ipaddress
import logging
import math
import os
import select
import signal
import sys
import termios
import time
import tty
from pathlib import Path

import yaml

from urkit import load_config, resolve_config
from urkit.cli.colors import blue, cyan, dim, green, red, yellow
from urkit.cli.connection_monitor import ConnectionMonitor
from urkit.cli.points import _interactive_points_filter
from urkit.exceptions import URKitConnectionError
from urkit.connection import (
    _connect_dashboard,
    _dashboard_command,
    _ping,
)
from urkit.exceptions import GripperError, MotionError, PointError, URKitConnectionError as ConnectionError
from urkit.geometry import MoveFrame, orient_tcp_down
from urkit.gripper.presets import DigitalGripperConfig, GripperPreset, PRESETS
from urkit.motion import FreedriveMode
from urkit.robot import URRobot

logger = logging.getLogger(__name__)

# Module-level monitor reference — set by _teach_pendant() so input helpers
# (_filter_select_points, _read_input) can check for faults without threading
# the parameter through every function.
_cli_monitor: "ConnectionMonitor | None" = None

# Default configuration path — resolved relative to the calling script's directory
def _resolve_default_config_path() -> Path:
    """Resolve the default config.yaml path for save operations."""
    resolved = resolve_config()
    if resolved is not None:
        return resolved
    return Path.cwd() / "config.yaml"

# Default step sizes
_DEFAULT_LINEAR_STEP = 0.005       # 5mm
_DEFAULT_LINEAR_STEP_MIN = 0.0001  # 0.1mm
_DEFAULT_LINEAR_STEP_MAX = 0.05    # 50mm (5cm)
_DEFAULT_ANGULAR_STEP = math.radians(1)  # 1 degree in radians
_DEFAULT_ANGULAR_STEP_MIN = math.radians(0.1)  # 0.1 degrees
_DEFAULT_ANGULAR_STEP_MAX = math.radians(25)   # 25 degrees

# Safe motion limits (UR protective stop thresholds)
_MAX_VEL = 3.0        # m/s
_MAX_ACC = 6.0        # m/s²
_MAX_ANG_VEL = 1.5    # rad/s
_MAX_ANG_ACC = 3.0    # rad/s²

# ------------------------------------------------------------------
# Dynamic velocity/acceleration from step size
# ------------------------------------------------------------------


def _compute_vel_acc(
    linear_step: float,
    angular_step: float,
    is_angular: bool = False,
) -> tuple[float, float]:
    """Compute velocity & acceleration from step size for ~constant travel time.

    Scales so the robot reaches the target in roughly the same time
    regardless of step size, capped at safe limits to avoid protective stops.

    Args:
        linear_step: Current linear step in meters.
        angular_step: Current angular step in radians.
        is_angular: If True, compute for angular (orientation) move.

    Returns:
        (velocity, acceleration) tuple.
    """
    if is_angular:
        vel = min(angular_step * 50.0, _MAX_ANG_VEL)
        acc = min(vel * 3.0, _MAX_ANG_ACC)
    else:
        vel = min(linear_step * 30.0, _MAX_VEL)
        acc = min(vel * 3.0, _MAX_ACC)
    return vel, acc

def _save_config(config: dict, path: str | Path | None = None) -> None:
    """Write configuration to config.yaml.

    Args:
        config: Configuration dict to save.
        path: Explicit path. Falls back to resolved default config path.
    """
    try:
        config_path = Path(path) if path is not None else _resolve_default_config_path()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
        logger.info("Config saved to %s", config_path)
    except Exception as e:
        logger.warning("Failed to save config: %s", e)


def _validate_ip(ip: str) -> bool:
    """Check if a string is a valid IPv4 address."""
    try:
        ipaddress.IPv4Address(ip)
        return True
    except (ipaddress.AddressValueError, ValueError):
        return False





# ------------------------------------------------------------------
# Raw terminal I/O
# ------------------------------------------------------------------

class _RawTerminal:
    """Manage raw terminal mode with tcgetattr/tcsetattr.

    Context-manager based: enters raw mode on __enter__, restores on __exit__.
    Single-character non-blocking reads via getkey().
    """

    def __enter__(self) -> "_RawTerminal":
        self._old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())
        return self

    def __exit__(self, *args) -> None:
        if hasattr(self, "_old_settings"):
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_settings)

    def getkey(self) -> str:
        """Read a single character without waiting for Enter.

        Returns:
            Single character string, or empty string if no input.
        """
        ready, _, _ = select.select([sys.stdin], [], [], 0.05)
        if ready:
            return sys.stdin.read(1)
        return ""


# ------------------------------------------------------------------
# UI rendering
# ------------------------------------------------------------------

def _draw_screen(
    robot: URRobot,
    state: dict,
    messages: list[str] | None = None,
) -> None:
    """Draw the full teach pendant screen.

    Single-screen layout matching point_saver style:
    - Header with title
    - Status section (position, orientation, speed, gripper)
    - Control reference (key bindings)
    """
    width = 72

    # Get live telemetry
    try:
        pose = robot.get_tcp_pose()
        joints = robot.get_joint_positions()
        tcp_force = robot.get_tcp_force()
    except Exception:
        pose = [0, 0, 0, 0, 0, 0]
        joints = [0, 0, 0, 0, 0, 0]
        tcp_force = [0, 0, 0, 0, 0, 0]

    gripper_state = "None"
    if robot.gripper:
        pos_mm = robot.gripper.get_position_mm()
        max_mm = robot.gripper.max_travel_mm()
        if pos_mm is not None and max_mm is not None and max_mm > 0:
            pct = int((max_mm - pos_mm) / max_mm * 100)
            gripper_state = f"{green('Connected')} {pos_mm:.1f}mm ({pct}%)"
        else:
            gripper_state = green("Connected")

    lines: list[str] = []

    # Header
    lines.append(dim("=" * width))
    lines.append(cyan(f"  === URKit Teach Pendant ===").center(width))
    lines.append(cyan(f"  IP: {robot.ip}").center(width))

    # Status section
    lines.append("")
    lw = 13  # label width for left alignment
    lines.append(f" {blue('Position'.ljust(lw))} X={pose[0]:+5.3f}  Y={pose[1]:+5.3f}  Z={pose[2]:+5.3f}")
    lines.append(f" {blue('Orientation'.ljust(lw))} R={math.degrees(pose[3]):+5.1f}  P={math.degrees(pose[4]):+5.1f}  Y={math.degrees(pose[5]):+5.1f}")
    lines.append(f" {blue('Step:'.ljust(lw))} L={state['linear_step']*1000:.1f}mm  A={math.degrees(state['angular_step']):.1f}°")
    lines.append(f" {blue('Frame:'.ljust(lw))} {green(state['move_frame'].name)} {dim('[M: toggle BASE/TOOL]')}")
    goto_label = "Cartesian" if state["goto_mode"] == "cartesian" else "Joint"
    lines.append(f" {blue('Go To:'.ljust(lw))} {green(goto_label)} {dim('[N: toggle Cartesian/Joint]')}")
    lines.append(f" {blue('Gripper:'.ljust(lw))} {gripper_state}")
    if state["freedrive"]:
        lines.append(f" {blue('Freedrive:'.ljust(lw))} {green('ON')} ({state['freedrive_mode'].name})")
    else:
        lines.append(f" {blue('Freedrive:'.ljust(lw))} {red('OFF')} {dim('[F: cycle ALL/XYZ+Rz]')}")
    slider_pct = int(state["speed_slider"] * 100)
    slider_color = green if state["speed_slider"] >= 0.5 else yellow if state["speed_slider"] >= 0.2 else red
    lines.append(f" {blue('Speed:'.ljust(lw))} {slider_color(f'{slider_pct}%')} {dim('[0: set]')}")

    # Robot fault status
    try:
        if robot.is_protective_stopped():
            lines.append(f"  {red('!! Protective Stop Active !!')}")
        if robot.is_emergency_stopped():
            lines.append(f"  {red('!! Emergency Stop Active !!')}")
    except Exception:
        pass

    # Status message line (only when there's something to show)
    if messages:
        status_msg = messages[-1][:width - 4]
        if status_msg.startswith("Error"):
            lines.append(f"  {red(status_msg)}")
        elif status_msg.startswith("Saved") or status_msg.startswith("Moved") or status_msg.startswith("Deleted") or status_msg.startswith("Renamed"):
            lines.append(f"  {green(status_msg)}")
        elif status_msg == "Cancelled":
            lines.append(f"  {yellow(status_msg)}")
        else:
            lines.append(f"  {status_msg}")

    lines.append(dim("-" * width))

    # Control reference
    lines.append(f"  {yellow('MOVE:')}    {yellow('W/S')}: ±X  {yellow('A/D')}: ±Y  {yellow('Q/E')}: ±Z")
    lines.append(f"  {yellow('ORIENT:')}  {yellow('U/O')}: ±Roll  {yellow('I/K')}: ±Pitch  {yellow('J/L')}: ±Yaw")
    lines.append(f"  {yellow('STEP:')}    {yellow('1')}: Linear (mm)  {yellow('2')}: Angular (°)  {yellow('.')}: Reset")
    lines.append(f"  {yellow('GRIPPER:')} {yellow('X')}: Open  {yellow('C')}: Close  {yellow('V')}: Position")
    lines.append(f"  {yellow('POINTS:')}  {yellow('B')}: Save  {yellow('G')}: Go To  {yellow('H')}: Delete  {yellow('R')}: Rename  {yellow('P')}: Explorer")
    lines.append(f"  {yellow('OTHER:')}   {yellow('F')}: Freedrive  {yellow('M')}: Frame  {yellow('N')}: GoTo Mode  {yellow('T')}: TCP Down")
    lines.append(f"  {yellow('      ')}   {yellow('0')}: Speed  {yellow('Y')}: Save Config")
    lines.append(f"  {yellow('EXIT:')}    {yellow('ESC')}")
    lines.append(dim("=" * width))

    # Clear and redraw
    sys.stdout.write("\033[2J\033[1;1H")
    sys.stdout.write("\n".join(lines) + "\n")
    sys.stdout.flush()


def _draw_help() -> None:
    """Print the full help overlay."""
    width = 72
    lines: list[str] = []

    lines.append("=" * width)
    lines.append("  === URKit Teach Pendant — Help ===".center(width))
    lines.append("=" * width)
    lines.append("")
    lines.append("  MOVE:")
    lines.append("    W/S    → X ± move")
    lines.append("    A/D    → Y ± move")
    lines.append("    Q/E    → Z ± move")
    lines.append("    U/O    → Roll ± move")
    lines.append("    I/K    → Pitch ± move")
    lines.append("    J/L    → Yaw ± move")
    lines.append("")
    lines.append("  STEP SIZE:")
    lines.append("    1/2    → Linear step ÷2/×2")
    lines.append("    3/4    → Angular step ÷2/×2")
    lines.append("")
    lines.append("  GRIPPER:")
    lines.append("    X      → Open")
    lines.append("    C      → Close")
    lines.append("    V      → Set position (mm)")
    lines.append("")
    lines.append("  POINTS:")
    lines.append("    B      → Save current pose")
    lines.append("    G      → Go to saved point (ask cartesian/joint)")
    lines.append("    H      → Delete saved point")
    lines.append("    R      → Rename saved point")
    lines.append("    P      → Open points explorer")
    lines.append("")
    lines.append("  OTHER:")
    lines.append("    F      → Cycle freedrive: OFF → ALL → XYZ+Rz → OFF")
    lines.append("    M      → Toggle move frame: BASE / TOOL")
    lines.append("    T      → Orient TCP downward (roll=180°)")
    lines.append("    0      → Set speed slider (0-100%)")
    lines.append("    Y      → Save config (IP, gripper, points path)")
    lines.append("")
    lines.append("  Exit   → ESC")
    lines.append("=" * width)
    print("\n".join(lines))


# ------------------------------------------------------------------
# Point submenus (restore canonical terminal for multi-char input)
# ------------------------------------------------------------------

def _configure_terminal() -> list:
    """Disable canonical mode and echo."""
    old_settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    return old_settings


def _restore_terminal(old_settings: list) -> None:
    """Restore canonical mode and echo."""
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


def _read_input(prompt: str, max_len: int = 30) -> str | None:
    """Read a line of input with backspace support.

    Uses cbreak mode with echo disabled — we handle all character
    display ourselves to avoid conflicts with terminal echo.

    Args:
        prompt: Prompt string.
        max_len: Maximum input length.

    Returns:
        Input string, or None if cancelled (ESC/empty).
    """
    old_settings = termios.tcgetattr(sys.stdin)
    tty.setcbreak(sys.stdin.fileno())
    # Disable echo — we handle character display ourselves to avoid conflicts
    settings = termios.tcgetattr(sys.stdin)
    settings[3] = settings[3] & ~termios.ECHO
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, settings)

    sys.stdout.write(prompt)
    sys.stdout.flush()

    name = ""
    while True:
        ready, _, _ = select.select([sys.stdin], [], [], 0.1)
        if not ready:
            if _cli_monitor and _cli_monitor.fault_detected:
                termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                raise URKitConnectionError(
                    f"Robot fault detected: {_cli_monitor._reason or 'RTDE connection lost'}. "
                    "RTDE connection lost."
                )
            continue
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            sys.stdout.write("\033[K")
            sys.stdout.flush()
            return None
        elif ch == "\x03":  # Ctrl+C
            sys.stdout.write("\033[K")
            sys.stdout.flush()
            return None
        elif ch == "\x08" or ch == "\x7f":  # Backspace
            if name:
                name = name[:-1]
                sys.stdout.write("\b \b")
                sys.stdout.flush()
        elif ch == "\n" or ch == "\r":
            sys.stdout.write("\033[K")
            sys.stdout.flush()
            break
        elif len(name) < max_len and ch.isprintable():
            name += ch
            sys.stdout.write(ch)
            sys.stdout.flush()

    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
    sys.stdout.write("\r\033[K\n")
    sys.stdout.flush()
    return name.strip()


def _submenu_save_point(
    robot: URRobot, messages: list[str]
) -> None:
    """Save current pose as a named point."""
    name = _read_input("  Point name: ")
    if not name:
        messages.append("Cancelled")
        return
    try:
        # Check if point already exists — ask for confirmation to overwrite
        if name in robot.point_names():
            confirm = _read_input(
                f"  Point '{name}' already exists. Overwrite? (y/n) "
            )
            if confirm != "y":
                messages.append("Cancelled")
                return

        robot.save_point(name)
        messages.append(f"Saved '{name}'")
    except URKitConnectionError:
        raise
    except Exception as e:
        messages.append(f"Error: {e}")


def _highlight_match(text: str, substring: str) -> str:
    """Highlight matching substring occurrences in text using ANSI colors."""
    if not substring:
        return text
    lower_text = text.lower()
    lower_sub = substring.lower()
    result = []
    start = 0
    while True:
        idx = lower_text.find(lower_sub, start)
        if idx == -1:
            result.append(text[start:])
            break
        result.append(text[start:idx])
        result.append("\033[1;32m" + text[idx:idx + len(substring)] + "\033[0m")
        start = idx + len(substring)
    return "".join(result)


def _filter_select_points(
    all_points: list[str],
    title: str,
) -> str | None:
    """Interactive point selector with real-time text filtering.

    User types characters to filter the list. Arrow keys navigate the
    filtered list. Matching text is highlighted in green. Press Enter
    to select, Backspace to remove chars, ESC to cancel.

    Returns:
        Selected point name, or None if cancelled.
    """
    filter_str = ""
    cursor = 0

    # Set terminal to raw mode once, outside the loop
    old_settings = termios.tcgetattr(sys.stdin)
    new_settings = termios.tcgetattr(sys.stdin)
    new_settings[3] = new_settings[3] & ~(termios.ICANON | termios.ECHO)
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, new_settings)

    fd = sys.stdin.fileno()

    try:
        while True:
            # Clear screen and draw
            sys.stdout.write("\033[2J\033[1;1H")
            sys.stdout.write(cyan(f"  === {title} ===") + "\n")
            sys.stdout.write(dim("  Arrows navigate · Type to filter · Enter select · ESC cancel") + "\n\n")
            sys.stdout.write(f"  {blue('Search:')} {filter_str}\n")
            sys.stdout.write("  " + dim("─" * 60) + "\n")

            filtered = [p for p in all_points if filter_str == "" or filter_str.lower() in p.lower()]

            # Clamp cursor to valid range
            if not filtered:
                cursor = 0
            elif cursor >= len(filtered):
                cursor = len(filtered) - 1

            if not filtered:
                sys.stdout.write(yellow(f"  No points match '{filter_str}'") + "\n")
                sys.stdout.write("\n  " + dim("Type to search for points...") + "\n")
            else:
                sys.stdout.write(blue("  Matching points:") + "\n")
                for i, p in enumerate(filtered):
                    marker = green("►") if i == cursor else " "
                    highlighted = _highlight_match(p, filter_str)
                    sys.stdout.write(f"    {marker} {highlighted}\n")

                sel = green("'" + filtered[cursor] + "'")
                sys.stdout.write(f"\n  {dim('Enter')} to select {sel}\n")

            sys.stdout.flush()

            ready, _, _ = select.select([fd], [], [], 0.1)
            if not ready:
                if _cli_monitor and _cli_monitor.fault_detected:
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
                    raise URKitConnectionError(
                        f"Robot fault detected: {_cli_monitor._reason or 'RTDE connection lost'}. "
                        "RTDE connection lost."
                    )
                continue

            # Read all bytes that arrived together — avoids Python text-mode
            # buffering silently consuming escape sequence bytes.
            # After select() says ready, os.read() gets everything the terminal
            # sent in one burst (e.g., \x1b[A for up-arrow). A second read
            # would block, so we only read once per select() notification.
            raw = os.read(fd, 64)
            if not raw:
                continue

            # Decode and parse sequentially, handling multi-byte escape sequences
            text = raw.decode("ascii", errors="replace")
            i = 0
            while i < len(text):
                ch = text[i]

                if ch == "\x1b":
                    # Check for CSI escape sequence (arrow keys send \x1b[A or \x1b[B)
                    if i + 2 < len(text) and text[i + 1] == "[":
                        key = text[i + 2]
                        if key == "A":
                            cursor = max(0, cursor - 1)
                        elif key == "B":
                            cursor = min(len(filtered) - 1, cursor + 1)
                        # Unrecognized CSI sequences are ignored
                        i += 3
                        continue
                    else:
                        # Bare ESC → cancel
                        return None

                if ch == "\n" or ch == "\r":
                    if filtered:
                        return filtered[cursor]
                    return None
                elif ch == "\x08" or ch == "\x7f":
                    filter_str = filter_str[:-1]
                elif ch == "\x03":
                    return None
                elif ch.isprintable() and len(filter_str) < 30:
                    filter_str += ch

                i += 1
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)


def _submenu_goto_point(
    robot: URRobot, state: dict, messages: list[str]
) -> None:
    """Go to a saved point using the current Go To mode."""
    try:
        point_names = robot.point_names()
        if not point_names:
            messages.append("No saved points")
            return

        name = _filter_select_points(point_names, "GO TO SAVED POINT")
        if not name:
            messages.append("Cancelled")
            return

        if state["freedrive"]:
            robot.disable_freedrive()
            state["freedrive"] = False

        is_cartesian = state["goto_mode"] == "cartesian"
        robot.move_to(name, linear=is_cartesian)
        mode_label = "cartesian" if is_cartesian else "joint"
        messages.append(f"Moved to '{name}' ({mode_label})")
    except URKitConnectionError:
        raise
    except Exception as e:
        messages.append(f"Error: {e}")


def _submenu_rename_point(
    robot: URRobot, messages: list[str]
) -> None:
    """Rename a saved point."""
    try:
        point_names = robot.point_names()
        if not point_names:
            messages.append("No saved points")
            return

        name = _filter_select_points(point_names, "RENAME SAVED POINT")
        if not name:
            messages.append("Cancelled")
            return

        new_name = _read_input("  New name: ")
        if not new_name:
            messages.append("Cancelled")
            return

        # Check if new name already exists — ask for confirmation
        if new_name in robot.point_names():
            confirm = _read_input(
                f"  Point '{new_name}' already exists. Overwrite? (y/n) "
            )
            if confirm != "y":
                messages.append("Cancelled")
                return

        # Rename via delete + save: load old point data, save as new name
        # The internal Points class handles this, but we don't expose it.
        # Use the raw _points object for rename (internal implementation).
        robot.rename_point(name, new_name)
        messages.append(f"Renamed '{name}' → '{new_name}'")
    except URKitConnectionError:
        raise
    except Exception as e:
        messages.append(f"Error: {e}")


def _submenu_delete_point(
    robot: URRobot, messages: list[str]
) -> None:
    """Delete a saved point."""
    try:
        point_names = robot.point_names()
        if not point_names:
            messages.append("No saved points")
            return

        name = _filter_select_points(point_names, "DELETE SAVED POINT")
        if not name:
            messages.append("Cancelled")
            return

        # Confirmation
        print("\033[2J\033[1;1H", end="")
        print("  === DELETE CONFIRMATION ===")
        print()
        print(f"  Delete point '{name}'?")
        print("  Type 'yes' to confirm:")
        confirm = _read_input("  > ")
        if confirm == "yes":
            robot.delete_point(name)
            messages.append(f"Deleted '{name}'")
        else:
            messages.append("Cancelled")
    except URKitConnectionError:
        raise
    except Exception as e:
        messages.append(f"Error: {e}")


def _submenu_explore_points(robot: URRobot, messages: list[str]) -> None:
    """Open the interactive points explorer."""
    try:
        if robot.points_db is None:
            messages.append("No points database configured")
            return
        
        all_points = robot.points_db.list()
        if not all_points:
            messages.append("No saved points")
            return
        
        _interactive_points_filter(robot.points_db, all_points)
        messages.append("Closed points explorer")
    except Exception as e:
        messages.append(f"Error: {e}")


# ------------------------------------------------------------------
# Key input helpers
# ------------------------------------------------------------------

def _key_to_delta(key: str, state: dict) -> list[float]:
    """Map a single movement key to a 6-element delta vector."""
    delta = [0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    if key == "w":
        delta[0] = state["linear_step"]
    elif key == "s":
        delta[0] = -state["linear_step"]
    elif key == "a":
        delta[1] = -state["linear_step"]
    elif key == "d":
        delta[1] = state["linear_step"]
    elif key == "q":
        delta[2] = state["linear_step"]
    elif key == "e":
        delta[2] = -state["linear_step"]
    elif key == "u":
        delta[3] = state["angular_step"]
    elif key == "o":
        delta[3] = -state["angular_step"]
    elif key == "i":
        delta[4] = state["angular_step"]
    elif key == "k":
        delta[4] = -state["angular_step"]
    elif key == "j":
        delta[5] = state["angular_step"]
    elif key == "l":
        delta[5] = -state["angular_step"]
    return delta


def _is_angular_key(key: str) -> bool:
    """Return True if the key controls an orientation axis."""
    return key in ("u", "o", "i", "j", "k", "l")


# ------------------------------------------------------------------
# Main interactive loop
# ------------------------------------------------------------------

class _ScreenLogHandler(logging.Handler):
    """Logging handler that appends messages to a list for display on screen."""
    def __init__(self, messages: list[str]) -> None:
        super().__init__()
        self._messages = messages
    def emit(self, record: logging.LogRecord) -> None:
        self._messages.append(self.format(record))


def _teach_pendant(
    robot: URRobot,
    *,
    config_path: str | Path | None = None,
    current_gripper_name: str | None = None,
    current_points_path: str | None = None,
) -> None:
    """Run the interactive teach pendant loop.

    Single-screen redraw loop matching point_saver style.

    Args:
        robot: Initialized URRobot instance.
    """
    state: dict = {
        "linear_step": _DEFAULT_LINEAR_STEP,
        "angular_step": _DEFAULT_ANGULAR_STEP,
        "freedrive": False,
        "freedrive_mode": FreedriveMode.ALL,
        "move_frame": robot.move_frame,
        "goto_mode": "cartesian",  # "cartesian" or "joint" for Go To
        "speed_slider": 1.0,
    }

    messages: list[str] = []

    # Redirect logging warnings/errors into screen messages (MUST be before
    # Points creation, as it may emit warnings)
    _urkit_logger = logging.getLogger("urkit")
    _urkit_logger.setLevel(logging.WARNING)
    _urkit_logger.propagate = False  # Don't leak to stderr via root logger
    _log_handler = _ScreenLogHandler(messages)
    _log_handler.setLevel(logging.WARNING)
    _log_handler.setFormatter(logging.Formatter("%(message)s"))
    _urkit_logger.addHandler(_log_handler)

    delta_keys = ("w", "s", "a", "d", "q", "e", "u", "o", "i", "j", "k", "l")

    # Throttle between movement steps — prevents terminal key repeat
    # from firing multiple moves on a single brief press
    _MOVE_THROTTLE = 0.05  # seconds
    last_move_t = 0.0

    if not sys.stdin.isatty():
        print("Error: stdin is not a terminal. Run from an interactive shell.")
        sys.exit(1)

    old_settings = termios.tcgetattr(sys.stdin)

    # SIGINT handler: restore terminal and exit when Ctrl+C pressed.
    # tty.setcbreak() keeps ISIG enabled, so Ctrl+C generates SIGINT.
    # os._exit() works even when blocked in C library code.
    def _sigint_handler(signum: int, frame: object) -> None:
        try:
            _restore_terminal(old_settings)
        except Exception:
            pass
        sys.stderr.write("\nInterrupted.\n")
        os._exit(0)

    signal.signal(signal.SIGINT, _sigint_handler)

    # Connection watchdog: detects faults and interrupts blocking calls.
    monitor = ConnectionMonitor(robot)
    monitor.start()
    _old_sigalrm = signal.signal(signal.SIGALRM, monitor.alarm_handler)
    _cli_monitor = monitor  # Global so input helpers can check for faults

    try:
        try:
            _configure_terminal()
            _draw_screen(robot, state, messages)

            # How often to refresh the screen while in freedrive (no key pressed)
            _FREEDRIVE_REFRESH_S = 0.5
            last_refresh = time.monotonic()

            while True:
                moved = False
                command_handled = False

                # --- Wait for a key ---
                while True:
                    ready, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if ready:
                        break

                    # Periodic refresh while in freedrive — robot may be moving by hand
                    if state["freedrive"]:
                        now = time.monotonic()
                        if now - last_refresh >= _FREEDRIVE_REFRESH_S:
                            last_refresh = now
                            _draw_screen(robot, state, messages)

                    # Check for fault detected by watchdog thread
                    if monitor.fault_detected:
                        raise URKitConnectionError(
                            f"Robot fault detected: {monitor._reason or 'RTDE connection lost'}. "
                            "RTDE connection lost."
                        )

                # --- Read key, draining buffered repeats ---
                # When a key is held, the terminal auto-repeats it into the
                # input buffer.  Reading only one character leaves stale repeats
                # behind — when the user switches from one movement key to
                # another, the last buffered copy of the old key fires one final
                # move in the wrong direction before the new key is read.
                # Fix: after select() signals ready, drain all immediately
                # available bytes (non-blocking) and use the last one.
                key = ""
                while True:
                    ready, _, _ = select.select([sys.stdin], [], [], 0.0)
                    if not ready:
                        break
                    ch = sys.stdin.read(1).lower()
                    if not ch:
                        break
                    key = ch
                if not key:
                    continue

                # Exit
                if key == "\x1b" or key == "\x03":
                    break

                # --- Movement keys (one press = one step) ---
                elif key in delta_keys:
                    # Throttle — skip rapid repeats from terminal key bounce
                    if time.monotonic() - last_move_t < _MOVE_THROTTLE:
                        continue
                    try:
                        if state["freedrive"]:
                            robot.disable_freedrive()
                            state["freedrive"] = False

                        delta = _key_to_delta(key, state)
                        has_angular = _is_angular_key(key)
                        vel, acc = _compute_vel_acc(
                            state["linear_step"], state["angular_step"], has_angular
                        )
                        robot.move_relative(delta, vel=vel, acc=acc, frame=state["move_frame"])
                        moved = True
                        last_move_t = time.monotonic()
                    except MotionError as e:
                        messages.append(f"Error: {e}")

                # --- Step size ---
                elif key == "1":
                    val = _read_input("  Linear step (mm): ")
                    try:
                        mm = float(val)
                        state["linear_step"] = max(mm / 1000, _DEFAULT_LINEAR_STEP_MIN)
                        state["linear_step"] = min(state["linear_step"], _DEFAULT_LINEAR_STEP_MAX)
                    except (ValueError, TypeError):
                        messages.append("Invalid step value")
                    command_handled = True

                elif key == "2":
                    val = _read_input("  Angular step (degrees): ")
                    try:
                        deg = float(val)
                        state["angular_step"] = max(math.radians(deg), _DEFAULT_ANGULAR_STEP_MIN)
                        state["angular_step"] = min(state["angular_step"], _DEFAULT_ANGULAR_STEP_MAX)
                    except (ValueError, TypeError):
                        messages.append("Invalid step value")
                    command_handled = True

                elif key == ".":
                    state["linear_step"] = _DEFAULT_LINEAR_STEP
                    state["angular_step"] = _DEFAULT_ANGULAR_STEP
                    messages.append("Step sizes reset to defaults")
                    command_handled = True

                # --- Freedrive ---
                elif key == "f":
                    if not state["freedrive"]:
                        try:
                            robot.enable_freedrive(FreedriveMode.ALL)
                            state["freedrive"] = True
                            state["freedrive_mode"] = FreedriveMode.ALL
                        except MotionError as e:
                            messages.append(f"Freedrive error: {e}")
                    else:
                        if state["freedrive_mode"] == FreedriveMode.ALL:
                            try:
                                robot.disable_freedrive()
                                robot.enable_freedrive(FreedriveMode.XYZ)
                                state["freedrive_mode"] = FreedriveMode.XYZ
                            except MotionError as e:
                                messages.append(f"Freedrive error: {e}")
                        else:
                            try:
                                robot.disable_freedrive()
                                state["freedrive"] = False
                            except MotionError as e:
                                messages.append(f"Freedrive error: {e}")
                    command_handled = True

                # --- Frame toggle ---
                elif key == "m":
                    if state["move_frame"] == MoveFrame.BASE:
                        state["move_frame"] = MoveFrame.TOOL
                    else:
                        state["move_frame"] = MoveFrame.BASE
                    robot.move_frame = state["move_frame"]
                    messages.append(f"Move frame: {state['move_frame'].name}")
                    command_handled = True

                # --- Go To mode toggle ---
                elif key == "n":
                    state["goto_mode"] = "joint" if state["goto_mode"] == "cartesian" else "cartesian"
                    messages.append(f"Go To mode: {state['goto_mode'].capitalize()}")
                    command_handled = True

                # --- TCP orient down ---
                elif key == "t":
                    if state["move_frame"] == MoveFrame.TOOL:
                        messages.append("TCP Down unavailable in TOOL frame")
                        command_handled = True
                    else:
                        try:
                            if state["freedrive"]:
                                robot.disable_freedrive()
                                state["freedrive"] = False
                            pose = robot.get_tcp_pose()
                            target = orient_tcp_down(pose)
                            robot.move_to(target, vel=0.5, acc=0.3)
                            messages.append("TCP oriented downward")
                        except MotionError as e:
                            messages.append(f"Error: {e}")
                        command_handled = True

                # --- Gripper ---
                elif key == "x":
                    if robot.gripper:
                        try:
                            robot.gripper.open()
                        except Exception as e:
                            messages.append(f"Gripper error: {e}")
                    else:
                        messages.append("No gripper configured")
                    command_handled = True

                elif key == "c":
                    if robot.gripper:
                        try:
                            robot.gripper.close()
                        except Exception as e:
                            messages.append(f"Gripper error: {e}")
                    else:
                        messages.append("No gripper configured")
                    command_handled = True

                elif key == "v":
                    if robot.gripper:
                        max_mm = getattr(robot.gripper, '_max_mm', None)
                        prompt = f"  Gripper position (0-{max_mm} mm): " if max_mm is not None else "  Gripper position (mm): "
                        val = _read_input(prompt)
                        try:
                            mm = float(val)
                            robot.gripper.set_position(mm)
                            messages.append(f"Gripper set to {mm:.1f} mm")
                        except (ValueError, TypeError):
                            messages.append("Invalid position value")
                        except Exception as e:
                            messages.append(f"Gripper error: {e}")
                    else:
                        messages.append("No gripper configured")
                    command_handled = True

                # --- Point management ---
                elif key == "b":
                    _submenu_save_point(robot, messages)
                    command_handled = True
                elif key == "g":
                    _submenu_goto_point(robot, state, messages)
                    command_handled = True
                elif key == "h":
                    _submenu_delete_point(robot, messages)
                    command_handled = True
                elif key == "r":
                    _submenu_rename_point(robot, messages)
                    command_handled = True
                elif key == "p":
                    _submenu_explore_points(robot, messages)
                    command_handled = True

                # --- Speed slider ---
                elif key == "0":
                    val = _read_input("  Speed slider (0-100%): ")
                    try:
                        pct = float(val)
                        factor = max(0.0, min(pct / 100.0, 1.0))
                        robot.set_speed_slider(factor)
                        state["speed_slider"] = factor
                        messages.append(f"Speed slider: {int(factor * 100)}%")
                    except (ValueError, TypeError):
                        messages.append("Invalid speed value")
                    except MotionError as e:
                        messages.append(f"Error: {e}")
                    command_handled = True

                # --- Save config ---
                elif key == "y":
                    save_cfg: dict = {}
                    save_cfg["robot_ip"] = robot.ip
                    if current_gripper_name:
                        save_cfg["gripper"] = current_gripper_name
                    if current_points_path:
                        save_cfg["points_path"] = current_points_path
                    _save_config(save_cfg, config_path)
                    target = Path(config_path) if config_path else _resolve_default_config_path()
                    messages.append(f"Config saved to {target}")
                    command_handled = True

                # --- Redraw after movement or command ---
                if moved or command_handled:
                    _draw_screen(robot, state, messages)
                    last_refresh = time.monotonic()
                    messages = []

        except URKitConnectionError as e:
            # Robot fault detected by monitoring thread
            print(f"\n{red('Fault:')} {e}")
        finally:
            # Stop monitor and restore signal handler
            _cli_monitor = None
            monitor.stop()
            signal.signal(signal.SIGALRM, _old_sigalrm)

    finally:
        _urkit_logger.removeHandler(_log_handler)
        _urkit_logger.propagate = True
        # Restore terminal
        try:
            _restore_terminal(old_settings)
        except Exception:
            pass
        print("\n  Exiting teach pendant.")


def teach_command(args) -> None:
    """Execute the teach pendant command.

    Args:
        args: Parsed arguments from argparse (with teach subcommand attributes).
    """

    # Configure logging
    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format="%(name)s - %(levelname)s - %(message)s",
        )
    else:
        logging.basicConfig(level=logging.WARNING)

    # Load config
    config = load_config(args.config)

    # Resolve effective values: CLI arg > config > None
    ip = args.ip or config.get("robot_ip")
    gripper_name = args.gripper or config.get("gripper")
    # "none" is an explicit CLI override — don't fall through to config
    if gripper_name and gripper_name.lower() == "none":
        gripper_name = None
    points_path = args.points or config.get("points_path") or "points.db"

    # Resolve gripper constructor params from config.yaml gripper_config section
    # and CLI --gripper-* flags (CLI overrides config)
    cfg = config.get("gripper_config") or {}
    gripper_kwargs: dict = {}
    if args.gripper_pin is not None:
        gripper_kwargs["pin"] = args.gripper_pin
    elif "pin" in cfg:
        gripper_kwargs["pin"] = cfg["pin"]
    if args.gripper_force is not None:
        gripper_kwargs["force"] = args.gripper_force
    elif "force" in cfg:
        gripper_kwargs["force"] = cfg["force"]
    if args.gripper_speed is not None:
        gripper_kwargs["speed"] = args.gripper_speed
    elif "speed" in cfg:
        gripper_kwargs["speed"] = cfg["speed"]
    if args.gripper_close_on_high is not None:
        gripper_kwargs["close_on_high"] = args.gripper_close_on_high == "true"
    elif "close_on_high" in cfg:
        gripper_kwargs["close_on_high"] = cfg["close_on_high"]

    # Resolve gripper string to config object
    gripper_config = None
    if gripper_name:
        preset = PRESETS.get(gripper_name.upper())
        if preset is not None:
            gripper_config = preset
        elif gripper_name == "digital":
            gripper_config = DigitalGripperConfig(
                pin=gripper_kwargs.pop("pin", 0),
                close_on_high=gripper_kwargs.pop("close_on_high", True),
            )

    if not ip:
        print("Error: No robot IP specified.")
        print("  Usage: urkit 192.168.1.100")
        print("  Or:    urkit (uses last-used IP from config)")
        print(f"  Config: {_resolve_default_config_path()}")
        sys.exit(1)

    # Validate IP format before any connection attempt
    if not _validate_ip(ip):
        print(f"Error: \"{ip}\" is not a valid IPv4 address.")
        print("  Usage: urkit 192.168.1.100")
        sys.exit(1)

    # Quick ping check to verify reachability
    if not _ping(ip, timeout=2.0):
        print(f"Error: Robot at {ip} is not reachable.")
        print("  Check the IP address and network connection.")
        sys.exit(1)

    # Print resolved params
    print(f"Connecting to robot at {ip}...")
    if gripper_name:
        print(f"  Gripper: {gripper_name}")
    print(f"  Points:  {points_path}")

    # URRobot handles everything: safety recovery, remote mode check,
    # power on, brake release, program stop, and RTDE connection.
    try:
        robot = URRobot(
            ip=ip,
            points=points_path,
            gripper=gripper_config,
            **gripper_kwargs,
        )
        print(f"  Connected.", flush=True)
        if robot.activate_gripper():
            print(f"  Gripper activated.", flush=True)
    except ConnectionError as e:
        print(f"Connection error: {e}")
        if "RTDE" in str(e):
            print(
                "\n  The robot is reachable but RTDE could not connect.\n"
                "  This usually means Remote Control is not enabled.\n"
                "  On the teach pendant:\n"
                "    1. Go to Settings → System → Remote Control → Enable\n"
                "    2. Press the remote/local button for remote mode\n"
                f"    3. Then try: urkit {ip}"
            )
        sys.exit(1)

    try:
        _teach_pendant(
            robot,
            config_path=args.config,
            current_gripper_name=gripper_name,
            current_points_path=points_path,
        )
    except KeyboardInterrupt:
        pass
    finally:
        # Stop any running program on the robot
        try:
            s = _connect_dashboard(robot.ip, timeout=5.0)
            try:
                _dashboard_command(s, "stop", timeout=2.0)
            except ConnectionError:
                pass
            s.close()
        except ConnectionError:
            pass
        robot.disconnect()


if __name__ == "__main__":
    main()
