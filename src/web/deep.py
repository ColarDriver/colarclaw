"""WhatsApp Web — deep: session lifecycle, message processing, contact store.

Covers remaining bk/src/web/ files for full coverage.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Message processing pipeline ───

@dataclass
class WAIncomingMessage:
    """Full incoming WhatsApp message context."""
    id: str = ""
    from_number: str = ""
    from_name: str = ""
    to: str = ""
    body: str = ""
    timestamp: int = 0
    has_media: bool = False
    media_type: str | None = None
    media_url: str | None = None
    media_mime: str | None = None
    media_filename: str | None = None
    is_group: bool = False
    group_id: str = ""
    group_name: str = ""
    quoted_msg_id: str | None = None
    quoted_msg_body: str | None = None
    is_forwarded: bool = False
    is_status: bool = False
    is_broadcast: bool = False
    mentions: list[str] = field(default_factory=list)
    location: dict[str, float] | None = None
    vcard: str | None = None


def parse_wa_message(raw: dict[str, Any]) -> WAIncomingMessage:
    """Parse raw WhatsApp message to structured context."""
    msg = WAIncomingMessage()
    msg.id = raw.get("id", {}).get("_serialized", raw.get("id", ""))
    msg.from_number = raw.get("from", "").replace("@c.us", "").replace("@g.us", "")
    msg.from_name = raw.get("notifyName", "") or raw.get("_data", {}).get("notifyName", "")
    msg.to = raw.get("to", "").replace("@c.us", "").replace("@g.us", "")
    msg.body = raw.get("body", "")
    msg.timestamp = int(raw.get("timestamp", 0))
    msg.has_media = raw.get("hasMedia", False)
    msg.media_type = raw.get("type") if msg.has_media else None
    msg.is_group = "@g.us" in raw.get("from", "")
    msg.group_id = raw.get("from", "") if msg.is_group else ""
    msg.is_forwarded = raw.get("isForwarded", False)
    msg.is_status = raw.get("isStatus", False)
    msg.is_broadcast = raw.get("broadcast", False)
    msg.mentions = raw.get("mentionedIds", [])

    # Quoted message
    quoted = raw.get("_data", {}).get("quotedMsg")
    if quoted:
        msg.quoted_msg_id = quoted.get("id", {}).get("_serialized", "")
        msg.quoted_msg_body = quoted.get("body", "")

    # Location
    if raw.get("type") == "location":
        msg.location = {
            "latitude": raw.get("location", {}).get("latitude", 0),
            "longitude": raw.get("location", {}).get("longitude", 0),
        }

    # VCard
    if raw.get("type") == "vcard":
        msg.vcard = raw.get("vCardString", "")

    return msg


# ─── Dispatch ───

@dataclass
class WADispatchConfig:
    allowed_numbers: list[str] = field(default_factory=list)
    blocked_numbers: list[str] = field(default_factory=list)
    allowed_groups: list[str] = field(default_factory=list)
    auto_reply_private: bool = True
    require_mention_in_groups: bool = True


class WAMessageDispatcher:
    """Decide whether to process a WhatsApp message."""

    def __init__(self, config: WADispatchConfig, *, bot_number: str = ""):
        self._config = config
        self._bot_number = bot_number

    def should_process(self, msg: WAIncomingMessage) -> tuple[bool, str]:
        # Skip status messages
        if msg.is_status or msg.is_broadcast:
            return False, "status_or_broadcast"
        # Blocked?
        if msg.from_number in self._config.blocked_numbers:
            return False, "blocked"
        # Private chat
        if not msg.is_group:
            if self._config.allowed_numbers and msg.from_number not in self._config.allowed_numbers:
                return False, "not_in_allowlist"
            return True, "private"
        # Group
        if self._config.allowed_groups and msg.group_id not in self._config.allowed_groups:
            return False, "group_not_allowed"
        if self._config.require_mention_in_groups:
            if self._bot_number not in msg.mentions and f"@{self._bot_number}" not in msg.body:
                return False, "not_mentioned"
        return True, "group"


# ─── Contact store ───

class WAContactStore:
    """Manages WhatsApp contacts cache."""

    def __init__(self, store_path: str = ""):
        self._path = store_path or os.path.expanduser("~/.openclaw/wa-contacts.json")
        self._contacts: dict[str, dict[str, str]] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(self._path):
            try:
                with open(self._path) as f:
                    self._contacts = json.load(f)
            except Exception:
                pass

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w") as f:
            json.dump(self._contacts, f, indent=2)

    def update(self, number: str, name: str, **extra: str) -> None:
        self._contacts[number] = {"name": name, **extra, "updatedAt": str(int(time.time()))}
        self._save()

    def get_name(self, number: str) -> str:
        return self._contacts.get(number, {}).get("name", number)

    def list_all(self) -> list[dict[str, str]]:
        return [{"number": k, **v} for k, v in self._contacts.items()]


# ─── Media handling ───

async def download_wa_media(
    adapter: Any,
    message_id: str,
    *,
    dest_dir: str = "/tmp",
) -> str | None:
    """Download media from a WhatsApp message."""
    try:
        media_data = await adapter.download_media(message_id)
        if not media_data:
            return None
        
        mimetype = media_data.get("mimetype", "application/octet-stream")
        ext_map = {
            "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
            "audio/ogg": "ogg", "audio/mpeg": "mp3",
            "video/mp4": "mp4",
            "application/pdf": "pdf",
        }
        ext = ext_map.get(mimetype, "bin")
        filename = f"wa-{message_id[-8:]}.{ext}"
        path = os.path.join(dest_dir, filename)
        
        import base64
        data = base64.b64decode(media_data.get("data", ""))
        with open(path, "wb") as f:
            f.write(data)
        return path
    except Exception as e:
        logger.error(f"WA media download error: {e}")
        return None


# ─── Formatting ───

def format_wa_bold(text: str) -> str:
    return f"*{text}*"


def format_wa_italic(text: str) -> str:
    return f"_{text}_"


def format_wa_strikethrough(text: str) -> str:
    return f"~{text}~"


def format_wa_monospace(text: str) -> str:
    return f"```{text}```"


def format_wa_mention(number: str) -> str:
    return f"@{number}"


# ─── Session reconnect ───

@dataclass
class WAReconnectPolicy:
    max_retries: int = 5
    base_delay_ms: int = 5000
    max_delay_ms: int = 300_000
    backoff_factor: float = 2.0
    current_retry: int = 0

    @property
    def next_delay_ms(self) -> int:
        delay = int(self.base_delay_ms * (self.backoff_factor ** self.current_retry))
        return min(delay, self.max_delay_ms)

    def should_retry(self) -> bool:
        return self.current_retry < self.max_retries

    def record_failure(self) -> None:
        self.current_retry += 1

    def reset(self) -> None:
        self.current_retry = 0
