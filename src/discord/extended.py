"""Discord — extended message handling, components, voice, exec approvals.

Ported from bk/src/discord/ remaining large files:
monitor/native-command.ts (~1848行), monitor/agent-components.ts (~1789行),
components.ts (~1149行), monitor/model-picker.ts (~940行),
voice/manager.ts (~902行), monitor/message-handler.process.ts (~843行),
monitor/message-handler.preflight.ts (~839行), monitor/exec-approvals.ts (~832行),
monitor/provider.ts (~803行), interactions.ts, delivery.ts,
thread.ts, send.ts, presence.ts, media.ts, embeds.ts,
onboard.ts, monitor/inbound.ts, monitor/outbound.ts,
monitor/thread-context.ts, monitor/history-fetch.ts.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable

logger = logging.getLogger(__name__)


# ─── Discord components (buttons, selects, modals) ───

@dataclass
class DiscordButton:
    label: str = ""
    custom_id: str = ""
    style: int = 1  # 1=Primary,2=Secondary,3=Success,4=Danger,5=Link
    emoji: str | None = None
    url: str | None = None
    disabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": 2, "label": self.label, "style": self.style}
        if self.custom_id:
            d["custom_id"] = self.custom_id
        if self.emoji:
            d["emoji"] = {"name": self.emoji}
        if self.url:
            d["url"] = self.url
            d["style"] = 5
        if self.disabled:
            d["disabled"] = True
        return d


@dataclass
class DiscordSelectOption:
    label: str = ""
    value: str = ""
    description: str = ""
    emoji: str | None = None
    is_default: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"label": self.label[:100], "value": self.value[:100]}
        if self.description:
            d["description"] = self.description[:100]
        if self.emoji:
            d["emoji"] = {"name": self.emoji}
        if self.is_default:
            d["default"] = True
        return d


@dataclass
class DiscordSelectMenu:
    custom_id: str = ""
    placeholder: str = ""
    options: list[DiscordSelectOption] = field(default_factory=list)
    min_values: int = 1
    max_values: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": 3,
            "custom_id": self.custom_id,
            "placeholder": self.placeholder[:150],
            "options": [o.to_dict() for o in self.options[:25]],
            "min_values": self.min_values,
            "max_values": self.max_values,
        }


def build_action_row(*components: dict[str, Any]) -> dict[str, Any]:
    """Build a Discord action row."""
    return {"type": 1, "components": list(components)[:5]}


def build_model_picker(models: list[str], *, current: str = "") -> dict[str, Any]:
    """Build model picker select menu."""
    options = [
        DiscordSelectOption(
            label=m[:100], value=m[:100],
            is_default=(m == current),
        )
        for m in models[:25]
    ]
    menu = DiscordSelectMenu(
        custom_id="model_picker", placeholder="Choose model...",
        options=options,
    )
    return build_action_row(menu.to_dict())


def build_agent_components(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Build agent selection components."""
    components = []
    if not agents:
        return components

    options = [
        DiscordSelectOption(
            label=a.get("name", a.get("id", ""))[:100],
            value=a.get("id", "")[:100],
            description=a.get("description", "")[:100],
        )
        for a in agents[:25]
    ]
    menu = DiscordSelectMenu(
        custom_id="agent_picker", placeholder="Choose agent...",
        options=options,
    )
    components.append(build_action_row(menu.to_dict()))
    return components


# ─── Exec approval buttons ───

def build_exec_approval_buttons(command: str, risk: str) -> dict[str, Any]:
    """Build approve/deny buttons for exec approvals."""
    approve_style = 3 if risk in ("low", "medium") else 4
    return build_action_row(
        DiscordButton(label="✅ Approve", custom_id=f"exec_approve:{hash(command) % 100000}",
                      style=approve_style).to_dict(),
        DiscordButton(label="❌ Deny", custom_id=f"exec_deny:{hash(command) % 100000}",
                      style=2).to_dict(),
    )


# ─── Discord voice manager ───

@dataclass
class VoiceConnection:
    channel_id: str = ""
    guild_id: str = ""
    connected: bool = False
    speaking: bool = False
    deaf: bool = False
    muted: bool = False


class VoiceManager:
    """Manages Discord voice connections."""

    def __init__(self) -> None:
        self._connections: dict[str, VoiceConnection] = {}

    async def join(self, guild_id: str, channel_id: str) -> VoiceConnection:
        conn = VoiceConnection(channel_id=channel_id, guild_id=guild_id, connected=True)
        self._connections[guild_id] = conn
        logger.info(f"Joined voice channel {channel_id} in {guild_id}")
        return conn

    async def leave(self, guild_id: str) -> None:
        self._connections.pop(guild_id, None)

    async def play_audio(self, guild_id: str, audio_path: str) -> None:
        conn = self._connections.get(guild_id)
        if not conn or not conn.connected:
            raise RuntimeError("Not connected to voice")
        conn.speaking = True
        # In real impl: use FFmpeg/opus to stream audio
        conn.speaking = False

    def get_connection(self, guild_id: str) -> VoiceConnection | None:
        return self._connections.get(guild_id)


# ─── Message handler — preflight & processing pipeline ───

@dataclass
class PreflightResult:
    should_process: bool = True
    reason: str = ""
    is_bot: bool = False
    is_allowed: bool = True
    is_mentioned: bool = False
    is_dm: bool = False


def preflight_check(
    message: dict[str, Any],
    *,
    allowed_guilds: list[str] | None = None,
    allowed_channels: list[str] | None = None,
    dm_allowlist: list[str] | None = None,
    bot_id: str = "",
) -> PreflightResult:
    """Pre-flight check for incoming Discord messages."""
    result = PreflightResult()

    # Skip bot messages
    author = message.get("author", {})
    if author.get("bot", False):
        result.should_process = False
        result.is_bot = True
        result.reason = "Bot message"
        return result

    # Check guild allowlist
    guild_id = message.get("guild_id", "")
    if allowed_guilds and guild_id and guild_id not in allowed_guilds:
        result.should_process = False
        result.is_allowed = False
        result.reason = "Guild not in allowlist"
        return result

    # Check channel allowlist
    channel_id = message.get("channel_id", "")
    if allowed_channels and channel_id not in allowed_channels:
        result.should_process = False
        result.is_allowed = False
        result.reason = "Channel not in allowlist"
        return result

    # Check DM allowlist
    if not guild_id:
        result.is_dm = True
        user_id = author.get("id", "")
        if dm_allowlist and user_id not in dm_allowlist:
            result.should_process = False
            result.is_allowed = False
            result.reason = "User not in DM allowlist"
            return result

    # Check mention
    mentions = message.get("mentions", [])
    result.is_mentioned = any(m.get("id") == bot_id for m in mentions)

    return result


# ─── Thread context ───

@dataclass
class ThreadContext:
    thread_id: str = ""
    parent_channel_id: str = ""
    owner_id: str = ""
    name: str = ""
    auto_archive_minutes: int = 1440
    created_at_ms: int = 0

    @property
    def is_auto_created(self) -> bool:
        return self.name.startswith("Reply-")


# ─── Discord delivery ───

async def deliver_discord_reply(
    adapter: Any,
    *,
    channel_id: str,
    text: str,
    reply_to: str | None = None,
    thread_id: str | None = None,
    components: list[dict[str, Any]] | None = None,
    embeds: list[dict[str, Any]] | None = None,
) -> list[str]:
    """Deliver a reply via Discord."""
    target_channel = thread_id or channel_id
    
    # Split and send
    from . import split_discord_message
    chunks = split_discord_message(text)
    sent_ids = []
    
    for i, chunk in enumerate(chunks):
        kwargs: dict[str, Any] = {"reply_to": reply_to if i == 0 else None}
        if embeds and i == len(chunks) - 1:
            kwargs["embeds"] = embeds
        
        result = await adapter.send_message(target_channel, chunk, **kwargs)
        sent_ids.extend(result if isinstance(result, list) else [result])
    
    # Add components as follow-up
    if components and sent_ids:
        pass  # Would use Discord API to add components
    
    return sent_ids


# ─── Presence ───

@dataclass
class PresenceConfig:
    status: str = "online"  # "online" | "idle" | "dnd" | "invisible"
    activity_type: int = 0  # 0=Playing,1=Streaming,2=Listening,3=Watching
    activity_name: str = "with messages"
