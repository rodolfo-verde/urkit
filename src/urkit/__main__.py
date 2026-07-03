"""urkit CLI entry point.

Usage:
    urkit teach 192.168.1.50
    urkit teach 192.168.1.50 --gripper=hand-e
    urkit points list
    urkit points list --filter "pick*"
"""

from __future__ import annotations

import argparse
import sys

from urkit.cli.teach import teach_command
from urkit.cli.points import points_command


def main() -> None:
    """Main CLI dispatcher for urkit subcommands."""
    parser = argparse.ArgumentParser(
        prog="urkit",
        description="URKit — Universal Robots e-Series control toolkit",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # teach subcommand
    teach_parser = subparsers.add_parser(
        "teach",
        help="Launch interactive teach pendant",
    )
    teach_parser.add_argument(
        "ip",
        type=str,
        nargs="?",
        default=None,
        help="Robot IP address (overrides config file)",
    )
    teach_parser.add_argument(
        "--gripper",
        type=str,
        default=None,
        choices=["2f-85", "2f-140", "hand-e", "digital", "none"],
        help="Gripper preset (overrides config file). Use 'none' to disable gripper",
    )
    teach_parser.add_argument(
        "--gripper-pin",
        type=int,
        default=None,
        help="Digital gripper output pin (overrides config file)",
    )
    teach_parser.add_argument(
        "--gripper-force",
        type=int,
        default=None,
        help="Robotiq gripper force 0-100 (overrides config file)",
    )
    teach_parser.add_argument(
        "--gripper-speed",
        type=int,
        default=None,
        help="Robotiq gripper speed 0-100 (overrides config file)",
    )
    teach_parser.add_argument(
        "--gripper-close-on-high",
        type=str,
        default=None,
        choices=["true", "false"],
        help="Digital gripper polarity: true=HIGH closes, false=LOW closes",
    )
    teach_parser.add_argument(
        "--points",
        type=str,
        default=None,
        help="Path to points.db file (overrides config file)",
    )
    teach_parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to config file (default: config.yaml in project root or CWD)",
    )
    teach_parser.add_argument(
        "-e", "--expert",
        action="store_true",
        default=False,
        help="Disable safety speed clamping (full speed for goto/tcp-down)",
    )
    teach_parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        default=False,
        help="Show verbose output (useful for debugging connection issues)",
    )

    # points subcommand
    points_parser = subparsers.add_parser(
        "points",
        help="Browse saved points interactively",
    )
    points_parser.add_argument(
        "points_path",
        type=str,
        nargs="?",
        default=None,
        help="Path to points.db file (defaults to points.db in config or current directory)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "teach":
        teach_command(args)
    elif args.command == "points":
        points_command(args)


def main_entry() -> None:
    """Entry point for console script."""
    main()


if __name__ == "__main__":
    main_entry()
