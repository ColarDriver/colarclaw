"""Signal — extended: daemon mode, group handling, trust TOFU, message delivery.

Ported from remaining bk/src/signal/ files.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class SignalGroupInfo:
    group_id: str = ""
    name: str = ""
    members: list[str] = field(default_factory=list)
    admins: list[str] = field(default_factory=list)
    is_blocked: bool = False


@dataclass
class SignalDaemonConfig:
    phone_number: str = ""
    signal_cli_path: str = "signal-cli"
    receive_mode: str = "json-rpc"  # "json-rpc" | "dbus"
    socket_path: str = ""


class SignalDaemon:
    """Signal CLI daemon mode (json-rpc)."""

    def __init__(self, config: SignalDaemonConfig):
        self.config = config
        self._process: subprocess.Popen | None = None
        self._running = False

    async def start(self) -> None:
        cmd = [
            self.config.signal_cli_path, "-u", self.config.phone_number,
            "daemon", "--json",
        ]
        if self.config.socket_path:
            cmd.extend(["--socket", self.config.socket_path])
        self._process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self._running = True
        logger.info(f"Signal daemon started (PID {self._process.pid})")

    async def stop(self) -> None:
        if self._process:
            self._process.terminate()
            self._process.wait(timeout=10)
        self._running = False

    async def read_messages(self) -> list[dict[str, Any]]:
        if not self._process or not self._process.stdout:
            return []
        messages = []
        try:
            while self._process.stdout.readable():
                line = self._process.stdout.readline()
                if not line:
                    break
                try:
                    messages.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        except Exception:
            pass
        return messages


class SignalTrustStore:
    """Manages Signal identity trust (TOFU, verified)."""

    def __init__(self) -> None:
        self._trusted: dict[str, str] = {}  # number -> fingerprint

    def trust(self, number: str, fingerprint: str) -> None:
        self._trusted[number] = fingerprint
    
    def is_trusted(self, number: str) -> bool:
        return number in self._trusted
    
    def verify(self, number: str, fingerprint: str) -> bool:
        stored = self._trusted.get(number)
        return stored == fingerprint


async def deliver_signal_reply(
    adapter: Any, *, recipient: str, text: str,
    group_id: str | None = None,
    quote_timestamp: int | None = None,
    attachments: list[str] | None = None,
) -> bool:
    return await adapter.send_message(
        recipient, text, group_id=group_id,
        quote_timestamp=quote_timestamp,
        attachment_paths=attachments,
    )
