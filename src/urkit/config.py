"""Configuration loading utilities.

Centralized YAML config loading shared by examples and the CLI.
Resolves ``config.yaml`` relative to the project root or an explicit path.

Usage::

    from urkit import load_config

    config = load_config()  # tries config.yaml in the project root
    config = load_config("/path/to/my.yaml")  # explicit path

    # Or create a robot directly from config:
    from urkit import URRobot
    robot = URRobot.from_config("config.yaml")
    robot = URRobot.from_config("config.yaml", ip="10.0.0.50")  # override IP
"""

from __future__ import annotations

from pathlib import Path

import yaml


__all__ = ["resolve_config", "load_config"]

_DEFAULT_NAME = "config.yaml"


def resolve_config(path: Path | str | None = None) -> Path | None:
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


def load_config(path: Path | str | None = None) -> dict:
    """Load a YAML config file and return it as a dict.

    Returns ``{}`` if the file is not found, empty, or invalid.

    Args:
        path: Explicit path to a YAML file. If ``None``, uses
            :func:`resolve_config` to search for ``config.yaml``.

    Returns:
        A dict with config keys, or ``{}`` on any error.
    """
    resolved = resolve_config(path)
    if resolved is None:
        return {}
    try:
        with open(resolved, "r") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}
