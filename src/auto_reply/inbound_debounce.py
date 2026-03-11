"""Auto-reply inbound debounce — ported from bk/src/auto-reply/inbound-debounce.ts."""
from __future__ import annotations

import asyncio
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def resolve_inbound_debounce_ms(cfg: Any, channel: str, override_ms: int | None = None) -> int:
    if isinstance(override_ms, (int, float)) and override_ms >= 0:
        return max(0, int(override_ms))
    messages = getattr(cfg, "messages", None)
    inbound = getattr(messages, "inbound", None) if messages else None
    if not inbound:
        return 0
    by_channel = getattr(inbound, "by_channel", None) or getattr(inbound, "byChannel", None)
    if isinstance(by_channel, dict) and channel in by_channel:
        v = by_channel[channel]
        if isinstance(v, (int, float)):
            return max(0, int(v))
    base = getattr(inbound, "debounce_ms", None) or getattr(inbound, "debounceMs", None)
    if isinstance(base, (int, float)):
        return max(0, int(base))
    return 0


class InboundDebouncer:
    """Buffers inbound items and flushes after debounce delay."""

    def __init__(
        self,
        debounce_ms: int,
        build_key: Callable[[Any], str | None],
        on_flush: Callable[[list[Any]], Any],
        should_debounce: Callable[[Any], bool] | None = None,
        resolve_debounce_ms: Callable[[Any], int | None] | None = None,
        on_error: Callable[[Exception, list[Any]], None] | None = None,
    ):
        self._default_debounce_ms = max(0, debounce_ms)
        self._build_key = build_key
        self._on_flush = on_flush
        self._should_debounce = should_debounce
        self._resolve_debounce_ms = resolve_debounce_ms
        self._on_error = on_error
        self._buffers: dict[str, dict[str, Any]] = {}

    def _get_debounce_ms(self, item: Any) -> int:
        if self._resolve_debounce_ms:
            resolved = self._resolve_debounce_ms(item)
            if isinstance(resolved, (int, float)):
                return max(0, int(resolved))
        return self._default_debounce_ms

    async def _flush_buffer(self, key: str) -> None:
        buf = self._buffers.pop(key, None)
        if not buf or not buf.get("items"):
            return
        task = buf.get("task")
        if task and not task.done():
            task.cancel()
        try:
            await self._on_flush(buf["items"])
        except Exception as err:
            if self._on_error:
                self._on_error(err, buf["items"])

    async def enqueue(self, item: Any) -> None:
        key = self._build_key(item)
        debounce_ms = self._get_debounce_ms(item)
        can_debounce = debounce_ms > 0 and (self._should_debounce(item) if self._should_debounce else True)

        if not can_debounce or not key:
            if key and key in self._buffers:
                await self._flush_buffer(key)
            try:
                await self._on_flush([item])
            except Exception as err:
                if self._on_error:
                    self._on_error(err, [item])
            return

        existing = self._buffers.get(key)
        if existing:
            existing["items"].append(item)
            existing["debounce_ms"] = debounce_ms
            task = existing.get("task")
            if task and not task.done():
                task.cancel()
            existing["task"] = asyncio.ensure_future(self._schedule_flush(key, debounce_ms))
        else:
            self._buffers[key] = {
                "items": [item],
                "debounce_ms": debounce_ms,
                "task": asyncio.ensure_future(self._schedule_flush(key, debounce_ms)),
            }

    async def _schedule_flush(self, key: str, delay_ms: int) -> None:
        await asyncio.sleep(delay_ms / 1000)
        await self._flush_buffer(key)

    async def flush_key(self, key: str) -> None:
        await self._flush_buffer(key)
