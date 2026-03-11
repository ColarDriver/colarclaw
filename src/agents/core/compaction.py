"""Conversation compaction / summarisation.

Ported from bk/src/agents/compaction.ts

When conversation history grows too long, replace older messages with
a compressed summary so the context window doesn't overflow.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger("openclaw.agents.compaction")

# Heuristic: assume ~4 chars per token
_CHARS_PER_TOKEN = 4
# Model context windows (conservative values, override per model as needed)
_DEFAULT_CONTEXT_CHARS = 200_000  # ~50k tokens


@dataclass
class CompactionResult:
    messages: list[dict]
    """Compacted message list (system prompt preserved, older msgs replaced)."""
    compacted: bool
    """Whether compaction was applied."""
    original_count: int
    summary_injected: bool = False


def estimate_chars(messages: list[dict]) -> int:
    """Rough character count across all message contents."""
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total += len(str(block.get("text", "")))
    return total


def _make_summary_message(summary_text: str) -> dict:
    return {
        "role": "assistant",
        "content": (
            "[CONTEXT SUMMARY – older messages compacted]\n"
            f"{summary_text}"
        ),
    }


def compact_messages(
    messages: list[dict],
    *,
    max_chars: int = _DEFAULT_CONTEXT_CHARS,
    keep_recent: int = 20,
    summary_text: str = "",
) -> CompactionResult:
    """Compact messages to fit within max_chars.

    Strategy:
    1. Always keep the system prompt (first message if role=system).
    2. Always keep the last `keep_recent` messages.
    3. If total chars > max_chars, drop everything in the middle and
       inject a summary message.

    Args:
        messages: Full message list.
        max_chars: Target char budget.
        keep_recent: Number of recent messages to always preserve.
        summary_text: Pre-computed summary to inject; if empty, a generic
                      placeholder is used.

    Returns:
        CompactionResult with compacted list and metadata.
    """
    original_count = len(messages)
    current_chars = estimate_chars(messages)

    if current_chars <= max_chars:
        return CompactionResult(
            messages=messages,
            compacted=False,
            original_count=original_count,
        )

    # Separate system prompt
    system: list[dict] = []
    rest: list[dict] = []
    for m in messages:
        if m.get("role") == "system" and not system and not rest:
            system.append(m)
        else:
            rest.append(m)

    recent = rest[-keep_recent:] if len(rest) > keep_recent else rest
    dropped_count = len(rest) - len(recent)

    if dropped_count == 0:
        # Can't compact further without losing recent messages
        logger.warning(
            "compaction: context (%d chars) exceeds budget (%d) but cannot compact further",
            current_chars,
            max_chars,
        )
        return CompactionResult(
            messages=messages,
            compacted=False,
            original_count=original_count,
        )

    summary = summary_text.strip() or (
        f"[{dropped_count} earlier messages were summarised and removed to fit the context window.]"
    )
    compacted = system + [_make_summary_message(summary)] + recent
    logger.info(
        "compaction: dropped %d messages (%d→%d chars)",
        dropped_count,
        current_chars,
        estimate_chars(compacted),
    )

    return CompactionResult(
        messages=compacted,
        compacted=True,
        original_count=original_count,
        summary_injected=True,
    )


# ---------------------------------------------------------------------------
# Async helper for use with LLM-generated summaries
# ---------------------------------------------------------------------------

async def compact_with_llm_summary(
    messages: list[dict],
    *,
    llm_call,  # async callable(messages) -> str
    max_chars: int = _DEFAULT_CONTEXT_CHARS,
    keep_recent: int = 20,
) -> CompactionResult:
    """Like compact_messages(), but generates the summary via LLM.

    Args:
        messages: Full message list.
        llm_call: Async callable that takes a message list and returns str summary.
        max_chars: Target char budget.
        keep_recent: Number of recent messages to preserve.
    """
    current_chars = estimate_chars(messages)
    if current_chars <= max_chars:
        return CompactionResult(
            messages=messages,
            compacted=False,
            original_count=len(messages),
        )

    # Identify messages to summarise
    system: list[dict] = []
    rest: list[dict] = []
    for m in messages:
        if m.get("role") == "system" and not system and not rest:
            system.append(m)
        else:
            rest.append(m)

    to_summarise = rest[:-keep_recent] if len(rest) > keep_recent else []
    if not to_summarise:
        return CompactionResult(
            messages=messages,
            compacted=False,
            original_count=len(messages),
        )

    try:
        summary_prompt = [
            {
                "role": "user",
                "content": (
                    "Summarise the following conversation in 2-5 sentences, "
                    "preserving key decisions, facts, and context:\n\n"
                    + "\n".join(
                        f"{m['role'].upper()}: {m.get('content','')}"
                        for m in to_summarise
                    )
                ),
            }
        ]
        summary_text = await llm_call(summary_prompt)
    except Exception as exc:
        logger.warning("LLM summary for compaction failed: %s; using placeholder", exc)
        summary_text = f"[{len(to_summarise)} earlier messages were summarised.]"

    return compact_messages(
        messages,
        max_chars=max_chars,
        keep_recent=keep_recent,
        summary_text=summary_text,
    )
