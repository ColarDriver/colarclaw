"""Infra exec_extended — ported from bk/src/infra/exec-host.ts,
exec-obfuscation-detect.ts, fetch.ts, fixed-window-rate-limit.ts.

Exec host communication, command obfuscation detection, fetch wrappers,
fixed-window rate limiting.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("infra.exec_extended")


# ─── exec-obfuscation-detect.ts ───

@dataclass
class ObfuscationDetection:
    detected: bool = False
    reasons: list[str] = field(default_factory=list)
    matched_patterns: list[str] = field(default_factory=list)


_OBFUSCATION_PATTERNS = [
    ("base64-pipe-exec",
     "Base64 decode piped to shell execution",
     re.compile(r"base64\s+(?:-d|--decode)\b.*\|\s*(?:sh|bash|zsh|dash|ksh|fish)\b", re.I)),
    ("hex-pipe-exec",
     "Hex decode (xxd) piped to shell execution",
     re.compile(r"xxd\s+-r\b.*\|\s*(?:sh|bash|zsh|dash|ksh|fish)\b", re.I)),
    ("printf-pipe-exec",
     "printf with escape sequences piped to shell execution",
     re.compile(r"printf\s+.*\\x[0-9a-f]{2}.*\|\s*(?:sh|bash|zsh|dash|ksh|fish)\b", re.I)),
    ("eval-decode",
     "eval with encoded/decoded input",
     re.compile(r"eval\s+.*(?:base64|xxd|printf|decode)", re.I)),
    ("base64-decode-to-shell",
     "Base64 decode piped to shell",
     re.compile(r"\|\s*base64\s+(?:-d|--decode)\b.*\|\s*(?:sh|bash|zsh|dash|ksh|fish)\b", re.I)),
    ("pipe-to-shell",
     "Content piped directly to shell interpreter",
     re.compile(r"\|\s*(?:sh|bash|zsh|dash|ksh|fish)\b(?:\s+[^|;\n\r]+)?\s*$", re.I | re.M)),
    ("command-substitution-decode-exec",
     "Shell -c with command substitution decode/obfuscation",
     re.compile(
         r'(?:sh|bash|zsh|dash|ksh|fish)\s+-c\s+["\'][^"\']*\$\([^)]*'
         r'(?:base64\s+(?:-d|--decode)|xxd\s+-r|printf\s+.*\\x[0-9a-f]{2})[^)]*\)[^"\']*["\']',
         re.I)),
    ("process-substitution-remote-exec",
     "Shell process substitution from remote content",
     re.compile(r"(?:sh|bash|zsh|dash|ksh|fish)\s+<\(\s*(?:curl|wget)\b", re.I)),
    ("source-process-substitution-remote",
     "source/. with process substitution from remote content",
     re.compile(r"(?:^|[;&\s])(?:source|\.)\s+<\(\s*(?:curl|wget)\b", re.I)),
    ("shell-heredoc-exec",
     "Shell heredoc execution",
     re.compile(r"(?:sh|bash|zsh|dash|ksh|fish)\s+<<-?\s*['\"]?[a-zA-Z_][\w-]*['\"]?", re.I)),
    ("octal-escape",
     "Bash octal escape sequences (potential command obfuscation)",
     re.compile(r"\$'(?:[^']*\\[0-7]{3}){2,}")),
    ("hex-escape",
     "Bash hex escape sequences (potential command obfuscation)",
     re.compile(r"\$'(?:[^']*\\x[0-9a-fA-F]{2}){2,}")),
    ("python-exec-encoded",
     "Python/Perl/Ruby with base64 or encoded execution",
     re.compile(r"(?:python[23]?|perl|ruby)\s+-[ec]\s+.*(?:base64|b64decode|decode|exec|system|eval)", re.I)),
    ("curl-pipe-shell",
     "Remote content (curl/wget) piped to shell execution",
     re.compile(r"(?:curl|wget)\s+.*\|\s*(?:sh|bash|zsh|dash|ksh|fish)\b", re.I)),
    ("var-expansion-obfuscation",
     "Variable assignment chain with expansion (potential obfuscation)",
     re.compile(r"(?:[a-zA-Z_]\w{0,2}=\S+\s*;\s*){2,}.*\$(?:[a-zA-Z_]|\{[a-zA-Z_])")),
]

_FALSE_POSITIVE_SUPPRESSIONS = [
    ({"curl-pipe-shell"},
     re.compile(r"curl\s+.*https?://(?:raw\.githubusercontent\.com/Homebrew|brew\.sh)\b", re.I)),
    ({"curl-pipe-shell"},
     re.compile(r"curl\s+.*https?://(?:raw\.githubusercontent\.com/nvm-sh/nvm|sh\.rustup\.rs|get\.docker\.com|install\.python-poetry\.org)\b", re.I)),
    ({"curl-pipe-shell"},
     re.compile(r"curl\s+.*https?://(?:get\.pnpm\.io|bun\.sh/install)\b", re.I)),
]


def detect_command_obfuscation(command: str) -> ObfuscationDetection:
    """Detect obfuscated or encoded commands."""
    if not command or not command.strip():
        return ObfuscationDetection()

    reasons: list[str] = []
    matched: list[str] = []

    for pat_id, description, regex in _OBFUSCATION_PATTERNS:
        if not regex.search(command):
            continue

        url_count = len(re.findall(r"https?://\S+", command))
        suppressed = url_count <= 1 and any(
            pat_id in exempt_ids and exempt_re.search(command)
            for exempt_ids, exempt_re in _FALSE_POSITIVE_SUPPRESSIONS
        )
        if suppressed:
            continue

        matched.append(pat_id)
        reasons.append(description)

    return ObfuscationDetection(
        detected=len(matched) > 0,
        reasons=reasons,
        matched_patterns=matched,
    )


# ─── exec-host.ts ───

@dataclass
class ExecHostRequest:
    command: list[str] = field(default_factory=list)
    raw_command: str | None = None
    cwd: str | None = None
    env: dict[str, str] | None = None
    timeout_ms: int | None = None
    needs_screen_recording: bool = False
    agent_id: str | None = None
    session_key: str | None = None
    approval_decision: str | None = None  # "allow-once" | "allow-always"


@dataclass
class ExecHostRunResult:
    exit_code: int | None = None
    timed_out: bool = False
    success: bool = False
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


async def request_exec_host_via_socket(
    socket_path: str,
    token: str,
    request: ExecHostRequest,
    timeout_ms: int = 20_000,
) -> dict[str, Any] | None:
    """Send an exec request to the exec host via Unix socket."""
    if not socket_path or not token:
        return None

    from ..gateway.lock import request_jsonl_socket

    request_json = json.dumps({
        "command": request.command,
        "rawCommand": request.raw_command,
        "cwd": request.cwd,
        "env": request.env,
        "timeoutMs": request.timeout_ms,
        "agentId": request.agent_id,
        "sessionKey": request.session_key,
        "approvalDecision": request.approval_decision,
    })

    nonce = secrets.token_hex(16)
    ts = int(time.time() * 1000)
    mac = hmac.new(token.encode(), f"{nonce}:{ts}:{request_json}".encode(), hashlib.sha256).hexdigest()

    payload = json.dumps({
        "type": "exec",
        "id": str(uuid.uuid4()),
        "nonce": nonce,
        "ts": ts,
        "hmac": mac,
        "requestJson": request_json,
    })

    def accept(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict) or value.get("type") != "exec-res":
            return None
        if value.get("ok") is True and value.get("payload"):
            return {"ok": True, "payload": value["payload"]}
        if value.get("ok") is False and value.get("error"):
            return {"ok": False, "error": value["error"]}
        return None

    return await request_jsonl_socket(socket_path, payload, timeout_ms, accept)


# ─── fixed-window-rate-limit.ts ───

class FixedWindowRateLimiter:
    """Fixed-window rate limiter."""

    def __init__(self, max_requests: int, window_ms: float, now_fn: Callable[[], float] | None = None):
        self._max = max(1, int(max_requests))
        self._window_ms = max(1, int(window_ms))
        self._now = now_fn or (lambda: time.time() * 1000)
        self._count = 0
        self._window_start = 0.0

    def consume(self) -> dict[str, Any]:
        now_ms = self._now()
        if now_ms - self._window_start >= self._window_ms:
            self._window_start = now_ms
            self._count = 0
        if self._count >= self._max:
            return {
                "allowed": False,
                "retry_after_ms": max(0, self._window_start + self._window_ms - now_ms),
                "remaining": 0,
            }
        self._count += 1
        return {
            "allowed": True,
            "retry_after_ms": 0,
            "remaining": max(0, self._max - self._count),
        }

    def reset(self) -> None:
        self._count = 0
        self._window_start = 0.0
