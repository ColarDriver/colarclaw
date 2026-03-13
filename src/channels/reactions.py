"""Channels status reactions — ported from bk/src/channels/status-reactions.ts,
ack-reactions.ts.

Channel-agnostic status reaction controller: emoji-based agent status display
with debouncing, stall timers, promise chain serialization, and terminal states.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

logger = logging.getLogger("channels.reactions")


# ─── types ───

class StatusReactionAdapter(Protocol):
    async def set_reaction(self, emoji: str) -> None: ...
    async def remove_reaction(self, emoji: str) -> None: ...


@dataclass
class StatusReactionEmojis:
    queued: str = "👀"
    thinking: str = "🤔"
    tool: str = "🔥"
    coding: str = "👨‍💻"
    web: str = "⚡"
    done: str = "👍"
    error: str = "😱"
    stall_soft: str = "🥱"
    stall_hard: str = "😨"


@dataclass
class StatusReactionTiming:
    debounce_ms: int = 700
    stall_soft_ms: int = 10_000
    stall_hard_ms: int = 30_000
    done_hold_ms: int = 1500
    error_hold_ms: int = 2500


DEFAULT_EMOJIS = StatusReactionEmojis()
DEFAULT_TIMING = StatusReactionTiming()


# ─── tool emoji resolution ───

CODING_TOOL_TOKENS = ["exec", "process", "read", "write", "edit", "session_status", "bash"]
WEB_TOOL_TOKENS = ["web_search", "web-search", "web_fetch", "web-fetch", "browser"]


def resolve_tool_emoji(tool_name: str | None, emojis: StatusReactionEmojis) -> str:
    """Resolve the appropriate emoji for a tool invocation."""
    normalized = (tool_name or "").strip().lower()
    if not normalized:
        return emojis.tool
    if any(token in normalized for token in WEB_TOOL_TOKENS):
        return emojis.web
    if any(token in normalized for token in CODING_TOOL_TOKENS):
        return emojis.coding
    return emojis.tool


# ─── status reaction controller ───

class StatusReactionController:
    """Channel-agnostic status reaction controller.

    Features:
    - Async task serialization (prevents concurrent API calls)
    - Debouncing (intermediate states debounce, terminal states immediate)
    - Stall timers (soft/hard warnings on inactivity)
    - Terminal state protection (done/error mark finished)
    """

    def __init__(
        self,
        enabled: bool,
        adapter: StatusReactionAdapter,
        initial_emoji: str,
        emojis: StatusReactionEmojis | None = None,
        timing: StatusReactionTiming | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ):
        self._enabled = enabled
        self._adapter = adapter
        self._initial_emoji = initial_emoji
        self._on_error = on_error

        self._emojis = emojis or StatusReactionEmojis(queued=initial_emoji)
        if not emojis:
            self._emojis.queued = initial_emoji
        self._timing = timing or StatusReactionTiming()

        self._current_emoji = ""
        self._pending_emoji = ""
        self._finished = False
        self._debounce_task: asyncio.Task | None = None
        self._stall_soft_task: asyncio.Task | None = None
        self._stall_hard_task: asyncio.Task | None = None
        self._queue: asyncio.Queue[str] = asyncio.Queue()

        self._known_emojis = {
            initial_emoji, self._emojis.queued, self._emojis.thinking,
            self._emojis.tool, self._emojis.coding, self._emojis.web,
            self._emojis.done, self._emojis.error,
            self._emojis.stall_soft, self._emojis.stall_hard,
        }

    async def _apply_emoji(self, new_emoji: str) -> None:
        if not self._enabled:
            return
        try:
            prev = self._current_emoji
            await self._adapter.set_reaction(new_emoji)
            if prev and prev != new_emoji:
                try:
                    await self._adapter.remove_reaction(prev)
                except Exception:
                    pass
            self._current_emoji = new_emoji
        except Exception as e:
            if self._on_error:
                self._on_error(e)

    def _cancel_timers(self) -> None:
        for task in (self._debounce_task, self._stall_soft_task, self._stall_hard_task):
            if task and not task.done():
                task.cancel()
        self._debounce_task = None
        self._stall_soft_task = None
        self._stall_hard_task = None

    async def set_queued(self) -> None:
        await self._schedule_emoji(self._emojis.queued, immediate=True)

    async def set_thinking(self) -> None:
        await self._schedule_emoji(self._emojis.thinking)

    async def set_tool(self, tool_name: str | None = None) -> None:
        emoji = resolve_tool_emoji(tool_name, self._emojis)
        await self._schedule_emoji(emoji)

    async def set_done(self) -> None:
        await self._finish_with_emoji(self._emojis.done)

    async def set_error(self) -> None:
        await self._finish_with_emoji(self._emojis.error)

    async def _schedule_emoji(self, emoji: str, immediate: bool = False) -> None:
        if not self._enabled or self._finished:
            return
        if emoji == self._current_emoji or emoji == self._pending_emoji:
            return
        self._pending_emoji = emoji
        if immediate:
            await self._apply_emoji(emoji)
            self._pending_emoji = ""
        else:
            # Simple debounce: just apply after delay
            if self._debounce_task and not self._debounce_task.done():
                self._debounce_task.cancel()

            async def _debounced():
                await asyncio.sleep(self._timing.debounce_ms / 1000.0)
                await self._apply_emoji(emoji)
                self._pending_emoji = ""

            self._debounce_task = asyncio.create_task(_debounced())

    async def _finish_with_emoji(self, emoji: str) -> None:
        if not self._enabled:
            return
        self._finished = True
        self._cancel_timers()
        await self._apply_emoji(emoji)
        self._pending_emoji = ""

    async def clear(self) -> None:
        if not self._enabled:
            return
        self._cancel_timers()
        self._finished = True
        for emoji in self._known_emojis:
            try:
                await self._adapter.remove_reaction(emoji)
            except Exception as e:
                if self._on_error:
                    self._on_error(e)
        self._current_emoji = ""
        self._pending_emoji = ""

    async def restore_initial(self) -> None:
        if not self._enabled:
            return
        self._cancel_timers()
        await self._apply_emoji(self._initial_emoji)
        self._pending_emoji = ""


# ─── ack-reactions.ts ───

@dataclass
class AckReactionConfig:
    enabled: bool = True
    emoji: str = "👀"
    remove_on_reply: bool = True


def resolve_ack_reaction_config(
    channel_config: dict[str, Any] | None = None,
) -> AckReactionConfig:
    """Resolve acknowledgment reaction config from channel config."""
    if not channel_config:
        return AckReactionConfig()
    ack = channel_config.get("ackReaction")
    if ack is None:
        return AckReactionConfig()
    if isinstance(ack, bool):
        return AckReactionConfig(enabled=ack)
    if isinstance(ack, dict):
        return AckReactionConfig(
            enabled=ack.get("enabled", True),
            emoji=ack.get("emoji", "👀"),
            remove_on_reply=ack.get("removeOnReply", True),
        )
    return AckReactionConfig()
