"""iMessage — extended: chat.db polling, delivery, group handling.

Ported from remaining bk/src/imessage/ files.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IMChatInfo:
    chat_id: str = ""
    display_name: str = ""
    is_group: bool = False
    participants: list[str] = field(default_factory=list)
    service: str = "iMessage"
    last_message_date: str = ""


class ChatDBReader:
    """Reads messages from macOS Messages chat.db (read-only)."""

    def __init__(self, db_path: str = ""):
        self._db_path = db_path or os.path.expanduser("~/Library/Messages/chat.db")

    @property
    def db_exists(self) -> bool:
        return os.path.exists(self._db_path)

    def get_recent_messages(self, *, limit: int = 50, since_rowid: int = 0) -> list[dict[str, Any]]:
        """Read recent messages from chat.db."""
        if not self.db_exists:
            return []
        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT m.ROWID, m.text, m.date, m.is_from_me,
                       h.id as sender, c.chat_identifier, c.display_name
                FROM message m
                LEFT JOIN handle h ON m.handle_id = h.ROWID
                LEFT JOIN chat_message_join cmj ON m.ROWID = cmj.message_id
                LEFT JOIN chat c ON cmj.chat_id = c.ROWID
                WHERE m.ROWID > ?
                ORDER BY m.date DESC
                LIMIT ?
            """, (since_rowid, limit))
            rows = cursor.fetchall()
            conn.close()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"chat.db read error: {e}")
            return []

    def get_chats(self) -> list[IMChatInfo]:
        """List available iMessage chats."""
        if not self.db_exists:
            return []
        try:
            import sqlite3
            conn = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute("""
                SELECT chat_identifier, display_name, service_name,
                       (SELECT COUNT(*) FROM chat_handle_join WHERE chat_id = chat.ROWID) as participants
                FROM chat
                ORDER BY ROWID DESC
                LIMIT 100
            """)
            chats = []
            for row in cursor.fetchall():
                chats.append(IMChatInfo(
                    chat_id=row["chat_identifier"] or "",
                    display_name=row["display_name"] or "",
                    is_group=int(row["participants"] or 0) > 1,
                    service=row["service_name"] or "iMessage",
                ))
            conn.close()
            return chats
        except Exception:
            return []


class IMPollingMonitor:
    """Polls chat.db for new messages."""

    def __init__(self, reader: ChatDBReader, *, poll_interval_ms: int = 2000):
        self._reader = reader
        self._poll_interval = poll_interval_ms
        self._last_rowid = 0
        self._running = False

    async def start(self, handler: Any) -> None:
        import asyncio
        self._running = True
        while self._running:
            messages = self._reader.get_recent_messages(since_rowid=self._last_rowid, limit=20)
            for msg in messages:
                rowid = msg.get("ROWID", 0)
                if rowid > self._last_rowid:
                    self._last_rowid = rowid
                if not msg.get("is_from_me", False):
                    try:
                        result = handler(msg)
                        if hasattr(result, '__await__'):
                            await result
                    except Exception as e:
                        logger.error(f"iMessage handler error: {e}")
            await asyncio.sleep(self._poll_interval / 1000)

    def stop(self) -> None:
        self._running = False
