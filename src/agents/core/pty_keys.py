"""PTY keys — ported from bk/src/agents/pty-keys.ts.

PTY key sequence definitions for terminal control.
"""
from __future__ import annotations

# Common control key sequences
CTRL_C = "\x03"
CTRL_D = "\x04"
CTRL_Z = "\x1a"
CTRL_L = "\x0c"
CTRL_A = "\x01"
CTRL_E = "\x05"
CTRL_K = "\x0b"
CTRL_U = "\x15"
CTRL_W = "\x17"
CTRL_R = "\x12"

# Arrow keys (escape sequences)
ARROW_UP = "\x1b[A"
ARROW_DOWN = "\x1b[B"
ARROW_RIGHT = "\x1b[C"
ARROW_LEFT = "\x1b[D"

# Special keys
BACKSPACE = "\x7f"
DELETE = "\x1b[3~"
HOME = "\x1b[H"
END = "\x1b[F"
PAGE_UP = "\x1b[5~"
PAGE_DOWN = "\x1b[6~"
TAB = "\t"
ENTER = "\r"
NEWLINE = "\n"

# Function keys
F1 = "\x1bOP"
F2 = "\x1bOQ"
F3 = "\x1bOR"
F4 = "\x1bOS"
F5 = "\x1b[15~"
F6 = "\x1b[17~"
F7 = "\x1b[18~"
F8 = "\x1b[19~"
F9 = "\x1b[20~"
F10 = "\x1b[21~"
F11 = "\x1b[23~"
F12 = "\x1b[24~"


def is_control_key(data: str) -> bool:
    """Check if data is a control key sequence."""
    if not data:
        return False
    return len(data) == 1 and ord(data[0]) < 32


def is_escape_sequence(data: str) -> bool:
    """Check if data starts with an escape sequence."""
    return data.startswith("\x1b")


def describe_key(data: str) -> str:
    """Return a human-readable description of a key sequence."""
    _KEY_NAMES = {
        CTRL_C: "Ctrl-C", CTRL_D: "Ctrl-D", CTRL_Z: "Ctrl-Z",
        CTRL_L: "Ctrl-L", CTRL_A: "Ctrl-A", CTRL_E: "Ctrl-E",
        ARROW_UP: "↑", ARROW_DOWN: "↓", ARROW_RIGHT: "→", ARROW_LEFT: "←",
        BACKSPACE: "Backspace", DELETE: "Delete",
        HOME: "Home", END: "End",
        TAB: "Tab", ENTER: "Enter", NEWLINE: "Newline",
    }
    return _KEY_NAMES.get(data, repr(data))
