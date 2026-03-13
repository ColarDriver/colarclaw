"""TUI — extended: search filter, scrollable list, key bindings, spinners.

Ported from remaining bk/src/tui/ files (~28 TS, ~5.4k lines).
"""
from __future__ import annotations

import sys
import time
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = [
    "SearchableSelect", "ScrollableList", "Spinner",
    "ProgressBar", "KeyHandler",
]


# ─── Searchable/filterable select ───

@dataclass
class SearchableOption:
    label: str = ""
    value: str = ""
    tags: list[str] = field(default_factory=list)
    score: float = 0


def filter_options(
    options: list[SearchableOption],
    query: str,
) -> list[SearchableOption]:
    """Filter options by search query."""
    if not query:
        return options
    query_lower = query.lower()
    scored = []
    for opt in options:
        label_lower = opt.label.lower()
        if query_lower in label_lower:
            # Exact match in label
            opt.score = 2.0 if label_lower.startswith(query_lower) else 1.0
            scored.append(opt)
        elif any(query_lower in t.lower() for t in opt.tags):
            opt.score = 0.5
            scored.append(opt)
    scored.sort(key=lambda o: -o.score)
    return scored


class SearchableSelect:
    """Interactive searchable selection menu."""

    def __init__(self, options: list[SearchableOption]):
        self._options = options
        self._filtered = list(options)
        self._query = ""
        self._selected_idx = 0

    def search(self, query: str) -> list[SearchableOption]:
        self._query = query
        self._filtered = filter_options(self._options, query)
        self._selected_idx = 0
        return self._filtered

    def select(self) -> SearchableOption | None:
        if 0 <= self._selected_idx < len(self._filtered):
            return self._filtered[self._selected_idx]
        return None

    def move_up(self) -> None:
        self._selected_idx = max(0, self._selected_idx - 1)

    def move_down(self) -> None:
        self._selected_idx = min(len(self._filtered) - 1, self._selected_idx + 1)

    def run_interactive(self) -> str | None:
        """Run interactive selection (simple fallback mode)."""
        print(f"\n  Search ({len(self._options)} items):")
        for i, opt in enumerate(self._options[:20]):
            marker = ">" if i == self._selected_idx else " "
            print(f"  {marker} {i + 1}. {opt.label}")
        if len(self._options) > 20:
            print(f"  ... and {len(self._options) - 20} more")
        try:
            query = input("  Filter: ").strip()
            if query:
                self.search(query)
                for i, opt in enumerate(self._filtered[:10]):
                    print(f"  {i + 1}. {opt.label}")
                choice = input("  Choice: ").strip()
                idx = int(choice) - 1 if choice else 0
                if 0 <= idx < len(self._filtered):
                    return self._filtered[idx].value
            else:
                choice = input("  Choice: ").strip()
                idx = int(choice) - 1 if choice else 0
                if 0 <= idx < len(self._options):
                    return self._options[idx].value
        except (ValueError, EOFError, KeyboardInterrupt):
            pass
        return None


# ─── Scrollable list ───

class ScrollableList:
    """A scrollable list for terminal display."""

    def __init__(self, items: list[str], *, visible_lines: int = 20):
        self._items = items
        self._visible = visible_lines
        self._offset = 0

    @property
    def total(self) -> int:
        return len(self._items)

    def scroll_up(self, lines: int = 1) -> None:
        self._offset = max(0, self._offset - lines)

    def scroll_down(self, lines: int = 1) -> None:
        max_offset = max(0, len(self._items) - self._visible)
        self._offset = min(max_offset, self._offset + lines)

    def page_up(self) -> None:
        self.scroll_up(self._visible)

    def page_down(self) -> None:
        self.scroll_down(self._visible)

    def render(self) -> str:
        visible = self._items[self._offset:self._offset + self._visible]
        lines = []
        for i, item in enumerate(visible):
            lines.append(f"  {self._offset + i + 1:4d}  {item}")
        # Scroll indicator
        if self._offset > 0:
            lines.insert(0, "  ↑ More above")
        if self._offset + self._visible < len(self._items):
            lines.append("  ↓ More below")
        return "\n".join(lines)


# ─── Spinner ───

class Spinner:
    """Terminal spinner animation."""

    FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, text: str = ""):
        self._text = text
        self._running = False
        self._thread: threading.Thread | None = None
        self._frame = 0

    def start(self, text: str = "") -> None:
        if text:
            self._text = text
        self._running = True
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()

    def stop(self, *, final_text: str = "") -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        sys.stdout.write(f"\r\033[K  ✓ {final_text or self._text}\n")
        sys.stdout.flush()

    def fail(self, text: str = "") -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        sys.stdout.write(f"\r\033[K  ✗ {text or self._text}\n")
        sys.stdout.flush()

    def update(self, text: str) -> None:
        self._text = text

    def _spin(self) -> None:
        while self._running:
            frame = self.FRAMES[self._frame % len(self.FRAMES)]
            sys.stdout.write(f"\r\033[K  {frame} {self._text}")
            sys.stdout.flush()
            self._frame += 1
            time.sleep(0.08)


# ─── Progress bar ───

class ProgressBar:
    """Terminal progress bar."""

    def __init__(self, total: int, *, width: int = 30, label: str = ""):
        self._total = max(total, 1)
        self._current = 0
        self._width = width
        self._label = label

    def update(self, current: int) -> None:
        self._current = min(current, self._total)
        self._render()

    def increment(self, amount: int = 1) -> None:
        self.update(self._current + amount)

    def finish(self) -> None:
        self.update(self._total)
        sys.stdout.write("\n")
        sys.stdout.flush()

    def _render(self) -> None:
        pct = self._current / self._total
        filled = int(self._width * pct)
        bar = "█" * filled + "░" * (self._width - filled)
        label = f" {self._label}" if self._label else ""
        sys.stdout.write(f"\r  [{bar}] {pct:.0%}{label} ({self._current}/{self._total})")
        sys.stdout.flush()


# ─── Key handler ───

class KeyHandler:
    """Simple key binding handler (for non-raw mode)."""

    def __init__(self) -> None:
        self._bindings: dict[str, Callable] = {}

    def bind(self, key: str, handler: Callable) -> None:
        self._bindings[key] = handler

    def handle(self, key: str) -> bool:
        if key in self._bindings:
            self._bindings[key]()
            return True
        return False
