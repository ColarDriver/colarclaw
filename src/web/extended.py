"""WhatsApp Web — extended: session, QR pairing, contacts, delivery.

Ported from remaining bk/src/web/ files.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WASession:
    """WhatsApp session state."""
    session_id: str = "default"
    authenticated: bool = False
    phone_number: str = ""
    push_name: str = ""
    platform: str = ""
    last_connected_ms: int = 0
    qr_code: str = ""


class WASessionManager:
    """Manages WhatsApp sessions (persistence, reconnect)."""

    def __init__(self, sessions_dir: str = ""):
        self._dir = sessions_dir or os.path.expanduser("~/.openclaw/sessions")
        self._sessions: dict[str, WASession] = {}

    def save(self, session: WASession) -> None:
        os.makedirs(self._dir, exist_ok=True)
        path = os.path.join(self._dir, f"wa-{session.session_id}.json")
        with open(path, "w") as f:
            json.dump({
                "sessionId": session.session_id,
                "authenticated": session.authenticated,
                "phoneNumber": session.phone_number,
                "pushName": session.push_name,
                "platform": session.platform,
                "lastConnected": session.last_connected_ms,
            }, f, indent=2)
        self._sessions[session.session_id] = session

    def load(self, session_id: str) -> WASession | None:
        path = os.path.join(self._dir, f"wa-{session_id}.json")
        if not os.path.exists(path):
            return None
        try:
            with open(path) as f:
                data = json.load(f)
            session = WASession(
                session_id=session_id,
                authenticated=data.get("authenticated", False),
                phone_number=data.get("phoneNumber", ""),
                push_name=data.get("pushName", ""),
                platform=data.get("platform", ""),
                last_connected_ms=data.get("lastConnected", 0),
            )
            self._sessions[session_id] = session
            return session
        except Exception:
            return None

    def delete(self, session_id: str) -> None:
        path = os.path.join(self._dir, f"wa-{session_id}.json")
        if os.path.exists(path):
            os.unlink(path)
        self._sessions.pop(session_id, None)


@dataclass
class WAContact:
    number: str = ""
    name: str = ""
    push_name: str = ""
    is_group: bool = False
    is_business: bool = False


@dataclass
class WAGroupInfo:
    group_id: str = ""
    name: str = ""
    description: str = ""
    owner: str = ""
    participants: list[str] = field(default_factory=list)
    admins: list[str] = field(default_factory=list)
    created_at_ms: int = 0


class WAQRPairingManager:
    """Manages QR code pairing flow."""

    def __init__(self) -> None:
        self._qr_data: str = ""
        self._paired = False
        self._callback: Any = None

    def on_qr(self, callback: Any) -> None:
        self._callback = callback

    async def handle_qr(self, qr_data: str) -> None:
        self._qr_data = qr_data
        if self._callback:
            result = self._callback(qr_data)
            if asyncio.iscoroutine(result):
                await result

    def render_qr_terminal(self, qr_data: str) -> str:
        """Render QR code as terminal text."""
        lines = ["Scan this QR code with WhatsApp:", ""]
        # Simplified QR rendering
        for i in range(0, min(len(qr_data), 100), 10):
            chunk = qr_data[i:i+10]
            line = "".join("██" if ord(c) % 2 == 0 else "  " for c in chunk)
            lines.append(f"  {line}")
        lines.append("")
        return "\n".join(lines)


async def deliver_whatsapp_reply(
    adapter: Any, *, to: str, text: str,
    quote_id: str | None = None,
    mentions: list[str] | None = None,
) -> str:
    return await adapter.send_message(to, text, quote_id=quote_id, mentions=mentions)
