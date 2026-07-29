"""Configuration loading utilities.

Centralized YAML config loading shared by examples and the CLI.
Resolves ``config.yaml`` relative to the project root or an explicit path.

Usage::

    from urkit import URRobot

    robot = URRobot.from_config("config.yaml")
    robot = URRobot.from_config("config.yaml", ip="10.0.0.50")  # override IP

Config YAML format
------------------

Minimal config::

    robot_ip: 192.168.1.50

Built-in gripper preset (string)::

    robot_ip: 192.168.1.50
    gripper: hand-e
    gripper_config:
        force: 50

Custom gripper with payload + TCP offset (dict)::

    robot_ip: 192.168.1.50
    gripper:
        mass: 0.5
        center_of_gravity: [0.0, 0.0, 0.0]
        tcp_offset: [0.0, 0.0, 0.175, 0.0, 0.0, 0.0]
        backend: none

Override physical properties on a built-in preset::

    robot_ip: 192.168.1.50
    gripper: hand-e
    gripper_config:
        mass: 1.5
        center_of_gravity: [0.0, 0.0, 0.08]

Full config reference::

    robot_ip: 192.168.1.50           # required
    points_path: points.db           # optional, SQLite waypoint DB
    gripper: hand-e                  # preset name, dict, or omit
    gripper_config:                  # optional overrides
        mass: 1.0                    # kg
        center_of_gravity: [0, 0, 0] # [x, y, z] in meters
        tcp_offset: [0, 0, 0.1, 0, 0, 0]  # [x, y, z, rx, ry, rz]
        force: 100                   # 0-100
        speed: 100                   # 0-100
        max_mm: 50                   # finger travel
    default_vel: 0.5                 # m/s
    default_acc: 0.3                 # m/s²
    ik_reference: home               # point name for IK reference posture
    expert_mode: false               # show advanced CLI commands
"""

from __future__ import annotations

from pathlib import Path

import yaml


__all__: list[str] = []

_DEFAULT_NAME = "config.yaml"


def _resolve_config(path: Path | str | None = None) -> Path | None:
    """Find and return a config file path, or ``None`` if not found.

    Args:
        path: Explicit path to a YAML file. If ``None``, searches for
            ``config.yaml`` in the project root first, then the CWD.

    Returns:
        A :class:`Path` if the file exists, otherwise ``None``.
    """
    if path is not None:
        p = Path(path)
        return p if p.exists() else None

    # Try project root (parent of src/urkit)
    project_root = Path(__file__).resolve().parent.parent.parent
    candidate = project_root / _DEFAULT_NAME
    if candidate.exists():
        return candidate

    # Fallback: CWD
    candidate = Path.cwd() / _DEFAULT_NAME
    if candidate.exists():
        return candidate

    return None


def _load_config(path: Path | str | None = None) -> dict[str, object]:
    """Load a YAML config file and return it as a dict.

    Returns ``{}`` if the file is not found, empty, or invalid.

    Args:
        path: Explicit path to a YAML file. If ``None``, searches for
            ``config.yaml`` in the project root, then the CWD.

    Returns:
        A dict with config keys, or ``{}`` on any error.
    """
    resolved = _resolve_config(path)
    if resolved is None:
        return {}
    try:
        with open(resolved, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}
