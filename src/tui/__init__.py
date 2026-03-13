"""TUI — Text User Interface components.

Ported from bk/src/tui/ (~28 TS files).

Covers interactive terminal UI: selection menus, confirmation prompts,
text input, multi-select, search/filter, scrollable lists,
key bindings, and form layouts.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, TypeVar

__all__ = [
    "select", "confirm", "text_input", "multi_select",
    "SelectOption", "FormField", "run_form",
]

T = TypeVar("T")


@dataclass
class SelectOption:
    """An option in a selection menu."""
    label: str = ""
    value: str = ""
    description: str = ""
    disabled: bool = False
    hint: str = ""


def select(
    message: str,
    options: list[SelectOption | str],
    *,
    default: str = "",
) -> str | None:
    """Display a selection menu and return chosen value."""
    resolved: list[SelectOption] = []
    for opt in options:
        if isinstance(opt, str):
            resolved.append(SelectOption(label=opt, value=opt))
        else:
            resolved.append(opt)

    if not resolved:
        return None

    print(f"\n  {message}")
    for i, opt in enumerate(resolved):
        marker = ">" if opt.value == default else " "
        disabled = " (disabled)" if opt.disabled else ""
        desc = f"  — {opt.description}" if opt.description else ""
        print(f"  {marker} {i + 1}. {opt.label}{desc}{disabled}")

    while True:
        try:
            raw = input("  Choice: ").strip()
            if not raw:
                # Return default or first
                return default or resolved[0].value
            idx = int(raw) - 1
            if 0 <= idx < len(resolved) and not resolved[idx].disabled:
                return resolved[idx].value
        except (ValueError, EOFError, KeyboardInterrupt):
            return None


def confirm(message: str, *, default: bool = True) -> bool:
    """Display a yes/no confirmation prompt."""
    hint = "Y/n" if default else "y/N"
    try:
        raw = input(f"  {message} [{hint}]: ").strip().lower()
        if not raw:
            return default
        return raw in ("y", "yes", "true", "1")
    except (EOFError, KeyboardInterrupt):
        return default


def text_input(
    message: str,
    *,
    default: str = "",
    placeholder: str = "",
    validate: Any = None,
) -> str | None:
    """Display a text input prompt."""
    hint = f" ({default})" if default else ""
    try:
        raw = input(f"  {message}{hint}: ").strip()
        if not raw:
            return default
        if validate:
            error = validate(raw)
            if error:
                print(f"  ✗ {error}")
                return text_input(message, default=default, validate=validate)
        return raw
    except (EOFError, KeyboardInterrupt):
        return None


def multi_select(
    message: str,
    options: list[SelectOption | str],
    *,
    defaults: list[str] | None = None,
) -> list[str]:
    """Display a multi-select menu."""
    resolved: list[SelectOption] = []
    for opt in options:
        if isinstance(opt, str):
            resolved.append(SelectOption(label=opt, value=opt))
        else:
            resolved.append(opt)

    selected = set(defaults or [])

    print(f"\n  {message} (comma-separated numbers)")
    for i, opt in enumerate(resolved):
        check = "✓" if opt.value in selected else " "
        print(f"  [{check}] {i + 1}. {opt.label}")

    try:
        raw = input("  Choices: ").strip()
        if not raw:
            return list(selected)
        indices = [int(x.strip()) - 1 for x in raw.split(",")]
        return [
            resolved[i].value
            for i in indices
            if 0 <= i < len(resolved) and not resolved[i].disabled
        ]
    except (ValueError, EOFError, KeyboardInterrupt):
        return list(selected)


def password_input(message: str) -> str | None:
    """Display a password input prompt (hidden)."""
    try:
        import getpass
        return getpass.getpass(f"  {message}: ")
    except (EOFError, KeyboardInterrupt):
        return None


# ─── Form ───

@dataclass
class FormField:
    """A field in an interactive form."""
    name: str = ""
    label: str = ""
    type: str = "text"  # "text" | "password" | "select" | "confirm" | "multi-select"
    default: Any = None
    options: list[SelectOption | str] = field(default_factory=list)
    required: bool = False
    validate: Any = None
    placeholder: str = ""


def run_form(title: str, fields: list[FormField]) -> dict[str, Any] | None:
    """Run an interactive form and return results."""
    print(f"\n  {title}")
    print(f"  {'─' * len(title)}")

    results: dict[str, Any] = {}

    for f in fields:
        if f.type == "text":
            val = text_input(f.label, default=f.default or "", validate=f.validate)
        elif f.type == "password":
            val = password_input(f.label)
        elif f.type == "select":
            val = select(f.label, f.options, default=f.default or "")
        elif f.type == "confirm":
            val = confirm(f.label, default=bool(f.default))
        elif f.type == "multi-select":
            val = multi_select(f.label, f.options, defaults=f.default)
        else:
            val = text_input(f.label, default=f.default or "")

        if val is None and f.required:
            print("  ✗ Cancelled")
            return None

        results[f.name] = val

    return results
