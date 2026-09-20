"""Dependency-free ANSI color helpers, shared by every terminal-facing script."""

from __future__ import annotations

import os

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
MAGENTA = "\033[95m"
CYAN = "\033[96m"
WHITE = "\033[97m"


def paint(text: str, *codes: str) -> str:
    """Wrap `text` in the given ANSI codes, resetting afterward."""
    return "".join(codes) + text + RESET


def enable_on_windows() -> None:
    """cmd.exe needs a nudge to interpret ANSI escapes; harmless elsewhere."""
    if os.name == "nt":
        os.system("")


def clear_screen() -> None:
    os.system("cls" if os.name == "nt" else "clear")


def divider(char: str = "-", width: int = 60) -> str:
    return paint(char * width, DIM)


def header(text: str, color: str = MAGENTA, width: int = 60) -> str:
    bar = "=" * width
    return f"\n{color}{bar}\n{text.center(width)}\n{bar}{RESET}\n"
