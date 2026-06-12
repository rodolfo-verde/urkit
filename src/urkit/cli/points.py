"""Points explorer — interactive terminal UI for browsing saved points.

Usage:
    urkit points
    Opens an interactive explorer with real-time search filtering.
"""

from __future__ import annotations

import difflib
import math
import select
import sys
import termios
from pathlib import Path

from rich.console import Console
from rich.table import Table

from urkit import load_config
from urkit.cli.colors import blue, cyan, dim, yellow
from urkit.points import Points


def points_command(args) -> None:
    """Execute the points command.

    Args:
        args: Parsed arguments from argparse (with points subcommand attributes).
    """
    _explore_points(args)


def _euclidean_distance(pose1: list, pose2: list) -> float:
    """Calculate Euclidean distance between two poses (using XYZ only)."""
    return math.sqrt(sum((pose1[i] - pose2[i]) ** 2 for i in range(3)))


def _sort_points_by_proximity(
    points_db: Points, point_names: list[str], reference_name: str = "home"
) -> list[str]:
    """Sort points by distance from a reference point, then alphabetically.
    
    Args:
        points_db: Loaded Points database.
        point_names: List of point names to sort.
        reference_name: Name of the reference point (default: "home").
    
    Returns:
        Sorted list of point names.
    """
    try:
        ref_pose = points_db[reference_name].pose
    except KeyError:
        # If reference point doesn't exist, use the first point
        if point_names:
            ref_pose = points_db[point_names[0]].pose
        else:
            return point_names

    def sort_key(name: str):
        try:
            pose = points_db[name].pose
            distance = _euclidean_distance(ref_pose, pose)
            return (distance, name)  # Sort by distance, then by name
        except KeyError:
            return (float("inf"), name)

    return sorted(point_names, key=sort_key)


def _sort_filtered_points(filtered: list[str], search_str: str) -> list[str]:
    """Sort filtered points by match quality: exact prefix, exact substring, then fuzzy.
    
    Args:
        filtered: List of point names matching the search.
        search_str: The search string.
    
    Returns:
        Sorted list with best matches first.
    """
    if not search_str:
        return filtered
    
    search_lower = search_str.lower()
    
    # Separate into: starts with, contains, and fuzzy matches
    starts_with = [p for p in filtered if p.lower().startswith(search_lower)]
    contains = [p for p in filtered if search_lower in p.lower() and not p.lower().startswith(search_lower)]
    fuzzy = [p for p in filtered if search_lower not in p.lower() and not p.lower().startswith(search_lower)]
    
    # Sort each group alphabetically
    starts_with.sort()
    contains.sort()
    
    # Sort fuzzy matches by similarity score
    fuzzy_scored = [(p, difflib.SequenceMatcher(None, search_lower, p.lower()).ratio()) for p in fuzzy]
    fuzzy_scored.sort(key=lambda x: (-x[1], x[0]))  # Sort by score (desc), then by name
    fuzzy = [p for p, _ in fuzzy_scored]
    
    return starts_with + contains + fuzzy


def _explore_points(args) -> None:
    """Launch interactive point explorer with real-time filtering.

    Args:
        args: Parsed arguments with points_path option.
    """
    # Resolve points path
    config = load_config()
    points_path = args.points_path or config.get("points_path") or "points.db"
    points_path = Path(points_path).resolve()

    if not points_path.exists():
        print(f"Error: Points database not found: {points_path}")
        sys.exit(1)

    try:
        points_db = Points(str(points_path))
        all_points = points_db.list()
    except Exception as e:
        print(f"Error loading points: {e}")
        sys.exit(1)

    if not all_points:
        print("No points saved yet.")
        return

    _interactive_points_filter(points_db, all_points)


def _interactive_points_filter(points_db: Points, all_points: list[str]) -> None:
    """Interactive point explorer with real-time table filtering.

    User types to filter, arrow keys scroll, ESC to quit.

    Args:
        points_db: Loaded Points database.
        all_points: List of all saved point names.
    """
    # Check if stdin is a TTY (interactive terminal)
    if not sys.stdin.isatty():
        print("Error: Interactive mode requires a terminal.")
        print("Run 'urkit points' in an interactive shell.")
        sys.exit(1)

    # Sort all points by proximity
    all_points_sorted = _sort_points_by_proximity(points_db, all_points)

    filter_str = ""
    scroll = 0  # Scroll offset for viewing
    needs_redraw = True  # Flag to redraw only when needed

    # Set terminal to raw mode
    old_settings = termios.tcgetattr(sys.stdin)
    new_settings = termios.tcgetattr(sys.stdin)
    new_settings[3] = new_settings[3] & ~(termios.ICANON | termios.ECHO)
    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, new_settings)

    fd = sys.stdin.fileno()
    # Rich auto-detects dark/light terminal theme
    console = Console(force_terminal=True)

    try:
        while True:
            # Only redraw if something changed
            if needs_redraw:
                # Filter points: exact matches first, then fuzzy
                search_lower = filter_str.lower()
                
                # First get all exact matches (starts with or contains)
                exact_matches = [p for p in all_points_sorted if filter_str == "" or search_lower in p.lower()]
                
                # Then add fuzzy matches (not already in exact)
                if filter_str:
                    fuzzy_matches = [p for p in all_points_sorted if search_lower not in p.lower()]
                    fuzzy_scored = [(p, difflib.SequenceMatcher(None, search_lower, p.lower()).ratio()) for p in fuzzy_matches]
                    fuzzy_scored = [(p, score) for p, score in fuzzy_scored if score > 0.6]  # Only good matches
                    fuzzy_scored.sort(key=lambda x: -x[1])  # Sort by score
                    fuzzy_matches = [p for p, _ in fuzzy_scored]
                    filtered = exact_matches + fuzzy_matches
                else:
                    filtered = exact_matches
                
                # Sort by match quality (starts with, contains, fuzzy)
                filtered = _sort_filtered_points(filtered, filter_str)

                # Clamp scroll to valid range
                if not filtered:
                    scroll = 0
                elif scroll >= len(filtered):
                    scroll = len(filtered) - 1
                elif scroll < 0:
                    scroll = 0

                # Clear screen and draw header
                sys.stdout.write("\033[2J\033[1;1H")
                sys.stdout.write(cyan("  === POINT EXPLORER ===") + "\n")
                sys.stdout.write(dim("  Type to search · ↑↓ scroll · ESC quit") + "\n\n")
                sys.stdout.write(f"  {blue('Search:')} {filter_str}\n\n")

                if not filtered:
                    sys.stdout.write(yellow(f"  No points match '{filter_str}'") + "\n")
                else:
                    # Build rich table with theme-aware colors
                    table = Table(show_header=True, header_style="bold", padding=(0, 1))
                    table.add_column("Name")
                    table.add_column("X (m)", justify="right")
                    table.add_column("Y (m)", justify="right")
                    table.add_column("Z (m)", justify="right")
                    table.add_column("RX (rad)", justify="right")
                    table.add_column("RY (rad)", justify="right")
                    table.add_column("RZ (rad)", justify="right")

                    for point_name in filtered:
                        try:
                            point = points_db[point_name]
                            pose = point.pose
                            table.add_row(
                                point_name,
                                f"{pose[0]:7.4f}",
                                f"{pose[1]:7.4f}",
                                f"{pose[2]:7.4f}",
                                f"{pose[3]:7.4f}",
                                f"{pose[4]:7.4f}",
                                f"{pose[5]:7.4f}",
                            )
                        except Exception:
                            table.add_row(point_name, *["ERROR"] * 6)

                    # Capture and print table with indentation
                    import io
                    buffer = io.StringIO()
                    temp_console = Console(file=buffer, force_terminal=True)
                    temp_console.print(table)
                    table_output = buffer.getvalue()
                    for line in table_output.splitlines():
                        sys.stdout.write("  " + line + "\n")

                sys.stdout.flush()
                needs_redraw = False

            # Check for input (blocking, no timeout)
            rlist, _, _ = select.select([fd], [], [])
            if not rlist:
                continue

            # Read input
            try:
                ch = sys.stdin.read(1)
            except Exception:
                break

            if ch == "\x1b":  # ESC or arrow key
                # Use longer timeout to reliably detect arrow sequences
                rlist, _, _ = select.select([fd], [], [], 0.2)
                if rlist:
                    # There's more input, likely an arrow sequence
                    try:
                        ch2 = sys.stdin.read(1)
                        if ch2 == "[":
                            ch3 = sys.stdin.read(1)
                            if ch3 == "A":  # Up arrow - scroll up
                                scroll = max(0, scroll - 1)
                                needs_redraw = True
                            elif ch3 == "B":  # Down arrow - scroll down
                                filtered = [p for p in all_points_sorted if filter_str == "" or filter_str.lower() in p.lower()]
                                scroll = min(len(filtered) - 1, scroll + 1) if filtered else 0
                                needs_redraw = True
                    except Exception:
                        break
                else:
                    # No more input, so this was just ESC — quit
                    break
            elif ch == "\x7f" or ch == "\x08":  # Backspace
                if filter_str:
                    filter_str = filter_str[:-1]
                    scroll = 0
                    needs_redraw = True
            elif ch.isprintable():
                filter_str += ch
                scroll = 0
                needs_redraw = True

    except KeyboardInterrupt:
        # Ctrl+C — exit gracefully without traceback
        pass
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)
        sys.stdout.write("\n")


