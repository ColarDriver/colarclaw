"""Polls — channel-agnostic poll types and parameter parsing.

Ported from bk/src/polls.ts (100行) + bk/src/poll-params.ts (89行).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "PollInput", "PollResult", "PollVote",
    "parse_poll_params", "validate_poll_input",
]


@dataclass
class PollInput:
    """Channel-agnostic poll definition."""
    question: str = ""
    options: list[str] = field(default_factory=list)
    max_selections: int = 1
    duration_seconds: int | None = None  # Telegram: 5-600s
    duration_hours: int | None = None    # Discord: hours
    anonymous: bool = True
    allows_multiple: bool = False


@dataclass
class PollVote:
    user_id: str = ""
    option_index: int = 0
    timestamp_ms: int = 0


@dataclass
class PollResult:
    poll_id: str = ""
    question: str = ""
    options: list[str] = field(default_factory=list)
    votes: dict[int, int] = field(default_factory=dict)  # option_index -> count
    voter_count: int = 0
    is_closed: bool = False


def parse_poll_params(text: str) -> PollInput | None:
    """Parse poll from text format:
    /poll Question?
    - Option 1
    - Option 2
    - Option 3
    """
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if not lines:
        return None

    question = lines[0]
    # Remove /poll prefix
    if question.lower().startswith("/poll"):
        question = question[5:].strip()
    if not question:
        return None

    options = []
    for line in lines[1:]:
        # Strip list markers
        cleaned = line.lstrip("-•●○").strip()
        if cleaned:
            options.append(cleaned)

    if len(options) < 2:
        return None

    return PollInput(question=question, options=options[:10])


def validate_poll_input(poll: PollInput) -> list[str]:
    """Validate a poll input. Returns list of error messages."""
    errors = []
    if not poll.question:
        errors.append("Question is required")
    if len(poll.question) > 300:
        errors.append("Question too long (max 300 chars)")
    if len(poll.options) < 2:
        errors.append("At least 2 options required")
    if len(poll.options) > 10:
        errors.append("Max 10 options allowed")
    for i, opt in enumerate(poll.options):
        if not opt:
            errors.append(f"Option {i+1} is empty")
        if len(opt) > 100:
            errors.append(f"Option {i+1} too long (max 100 chars)")
    if poll.duration_seconds is not None:
        if poll.duration_seconds < 5 or poll.duration_seconds > 600:
            errors.append("Duration must be 5-600 seconds")
    return errors
