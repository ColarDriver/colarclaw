"""Reply dispatcher — ported from bk/src/auto-reply/reply/reply-dispatcher.ts."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ReplyDispatcherOptions:
    on_reply: Callable[[str], Any] | None = None
    on_media: Callable[[str], Any] | None = None
    on_error: Callable[[Exception], None] | None = None


@dataclass
class ReplyDispatcherWithTypingOptions(ReplyDispatcherOptions):
    on_typing_start: Callable[[], None] | None = None
    on_typing_stop: Callable[[], None] | None = None


class ReplyDispatcher:
    """Manages reply dispatch lifecycle."""

    def __init__(self, options: ReplyDispatcherOptions | None = None):
        self._options = options or ReplyDispatcherOptions()
        self._completed = False
        self._idle_event = asyncio.Event()

    async def dispatch_text(self, text: str) -> None:
        if self._options.on_reply:
            result = self._options.on_reply(text)
            if hasattr(result, "__await__"):
                await result

    async def dispatch_media(self, url: str) -> None:
        if self._options.on_media:
            result = self._options.on_media(url)
            if hasattr(result, "__await__"):
                await result

    def mark_complete(self) -> None:
        self._completed = True
        self._idle_event.set()

    async def wait_for_idle(self) -> None:
        await self._idle_event.wait()

    @property
    def is_complete(self) -> bool:
        return self._completed


def create_reply_dispatcher(options: ReplyDispatcherOptions) -> ReplyDispatcher:
    return ReplyDispatcher(options)


def create_reply_dispatcher_with_typing(
    options: ReplyDispatcherWithTypingOptions,
) -> tuple[ReplyDispatcher, dict[str, Any], Callable[[], None]]:
    dispatcher = ReplyDispatcher(options)
    reply_options: dict[str, Any] = {}

    def mark_idle() -> None:
        dispatcher.mark_complete()

    return dispatcher, reply_options, mark_idle
