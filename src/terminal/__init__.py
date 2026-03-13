"""Terminal UI components.

Ported from bk/src/terminal/ (~13 TS files, ~906 lines).

Covers terminal table rendering, ANSI color palette, screen size detection,
text truncation, and safe ANSI wrapping.
"""
from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from typing import Any


# ─── Color palette ───

class Palette:
    """ANSI color palette for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    ITALIC = "\033[3m"
    UNDERLINE = "\033[4m"

    # Colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    GRAY = "\033[90m"

    # Bright
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"

    # Backgrounds
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"
    BG_YELLOW = "\033[43m"
    BG_BLUE = "\033[44m"

    @staticmethod
    def is_color_supported() -> bool:
        if os.environ.get("NO_COLOR"):
            return False
        if os.environ.get("FORCE_COLOR"):
            return True
        try:
            return os.isatty(1)
        except Exception:
            return False

    @classmethod
    def colorize(cls, text: str, color: str) -> str:
        if not cls.is_color_supported():
            return text
        return f"{color}{text}{cls.RESET}"

    @classmethod
    def success(cls, text: str) -> str:
        return cls.colorize(text, cls.GREEN)

    @classmethod
    def error(cls, text: str) -> str:
        return cls.colorize(text, cls.RED)

    @classmethod
    def warning(cls, text: str) -> str:
        return cls.colorize(text, cls.YELLOW)

    @classmethod
    def info(cls, text: str) -> str:
        return cls.colorize(text, cls.CYAN)

    @classmethod
    def dim(cls, text: str) -> str:
        return cls.colorize(text, cls.DIM)

    @classmethod
    def bold(cls, text: str) -> str:
        return cls.colorize(text, cls.BOLD)


# ─── Terminal size ───

def get_terminal_size() -> tuple[int, int]:
    """Get terminal columns and rows."""
    size = shutil.get_terminal_size(fallback=(80, 24))
    return size.columns, size.lines


# ─── Text wrapping and truncation ───

def truncate(text: str, max_width: int, *, ellipsis: str = "…") -> str:
    """Truncate text to fit within max_width."""
    if len(text) <= max_width:
        return text
    return text[:max_width - len(ellipsis)] + ellipsis


def strip_ansi(text: str) -> str:
    """Strip ANSI escape sequences from text."""
    import re
    return re.sub(r"\033\[[0-9;]*[a-zA-Z]", "", text)


def visible_length(text: str) -> int:
    """Get visible length of text (excluding ANSI sequences)."""
    return len(strip_ansi(text))


def pad_right(text: str, width: int) -> str:
    """Pad text to width, accounting for ANSI sequences."""
    vis_len = visible_length(text)
    if vis_len >= width:
        return text
    return text + " " * (width - vis_len)


# ─── Table rendering ───

@dataclass
class TableColumn:
    header: str = ""
    min_width: int = 0
    max_width: int = 0
    align: str = "left"  # "left" | "right" | "center"


def render_table(
    headers: list[str],
    rows: list[list[str]],
    *,
    max_col_width: int = 40,
    separator: str = "  ",
    use_color: bool = True,
) -> str:
    """Render a formatted table."""
    if not rows and not headers:
        return ""

    num_cols = len(headers)
    # Calculate widths
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < num_cols:
                widths[i] = max(widths[i], visible_length(str(cell)))

    # Apply max width
    widths = [min(w, max_col_width) for w in widths]

    lines: list[str] = []

    # Header
    header_cells = []
    for i, h in enumerate(headers):
        if use_color and Palette.is_color_supported():
            header_cells.append(Palette.bold(pad_right(h, widths[i])))
        else:
            header_cells.append(pad_right(h, widths[i]))
    lines.append(separator.join(header_cells))

    # Separator
    lines.append(separator.join("─" * w for w in widths))

    # Rows
    for row in rows:
        cells = []
        for i in range(num_cols):
            cell = str(row[i]) if i < len(row) else ""
            cell_display = truncate(cell, widths[i]) if visible_length(cell) > widths[i] else cell
            cells.append(pad_right(cell_display, widths[i]))
        lines.append(separator.join(cells))

    return "\n".join(lines)


def print_table(headers: list[str], rows: list[list[str]], **kwargs: Any) -> None:
    """Render and print a table."""
    print(render_table(headers, rows, **kwargs))


# ─── Status indicators ───

def status_icon(status: str) -> str:
    """Get a colored status icon."""
    icons = {
        "ok": Palette.success("✓"),
        "running": Palette.success("●"),
        "connected": Palette.success("●"),
        "warning": Palette.warning("⚠"),
        "error": Palette.error("✗"),
        "stopped": Palette.dim("○"),
        "disabled": Palette.dim("○"),
        "unknown": Palette.dim("?"),
    }
    return icons.get(status.lower(), Palette.dim("·"))
