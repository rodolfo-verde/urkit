"""Cross-platform terminal color helpers.

Uses colorama for Windows compatibility. Detects dark/light terminal
and adjusts colors for readability.
"""

from __future__ import annotations

import os

import colorama

colorama.init()

# ANSI codes (colorama makes these work on Windows)
RST = "\033[0m"
BOLD = "\033[1m"


def _is_dark_terminal() -> bool:
    """Detect if the terminal is using a dark background."""
    cfbg = os.environ.get("COLORFGBG", "")
    if cfbg and ":" in cfbg:
        try:
            bg = int(cfbg.split(":")[1])
            return bg in (0, 1, 2, 3, 4, 5, 6)
        except (ValueError, IndexError):
            pass
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("TERM_PROGRAM") == "vscode":
        theme = os.environ.get("VSCODE_THEME_COLORID", "")
        return "dark" in theme.lower()
    return True


# Two complete palettes
_DARK = {
    "DIM": "\033[2m",
    "GREEN": "\033[92m",
    "YELLOW": "\033[93m",
    "BLUE": "\033[94m",
    "CYAN": "\033[96m",
    "RED": "\033[91m",
    "WHITE": "\033[97m",
}

_LIGHT = {
    "DIM": "\033[2m",
    "GREEN": "\033[32m",
    "YELLOW": "\033[33m",
    "BLUE": "\033[34m",
    "CYAN": "\033[36m",
    "RED": "\033[31m",
    "WHITE": "\033[37m",
}

_PALETTE = _DARK if _is_dark_terminal() else _LIGHT

DIM = _PALETTE["DIM"]
GREEN = _PALETTE["GREEN"]
YELLOW = _PALETTE["YELLOW"]
BLUE = _PALETTE["BLUE"]
CYAN = _PALETTE["CYAN"]
RED = _PALETTE["RED"]
WHITE = _PALETTE["WHITE"]


def _wrap(text: str, *codes: str) -> str:
    """Wrap text with ANSI codes and reset."""
    return "".join(codes) + text + RST


def bold(text: str) -> str:
    return _wrap(text, BOLD)


def green(text: str) -> str:
    return _wrap(text, GREEN)


def yellow(text: str) -> str:
    return _wrap(text, YELLOW)


def blue(text: str) -> str:
    return _wrap(text, BLUE)


def cyan(text: str) -> str:
    return _wrap(text, CYAN)


def red(text: str) -> str:
    return _wrap(text, RED)


def dim(text: str) -> str:
    return _wrap(text, DIM)
