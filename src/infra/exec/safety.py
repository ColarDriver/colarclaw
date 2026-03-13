"""Infra exec — ported from bk/src/infra/exec-*.ts (16 files).

Exec safety: allowlist patterns, approval forwarding, command resolution,
obfuscation detection, safe-bin policy, exec host, wrapper resolution.
"""
from __future__ import annotations

import fnmatch
import os
import re
import shutil
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

# ─── exec-allowlist-pattern.ts ───

@dataclass
class ExecAllowlistEntry:
    pattern: str = ""
    kind: str = "glob"  # "glob" | "exact" | "prefix"


def match_exec_allowlist_entry(command: str, entry: ExecAllowlistEntry) -> bool:
    if entry.kind == "exact":
        return command == entry.pattern
    if entry.kind == "prefix":
        return command.startswith(entry.pattern)
    return fnmatch.fnmatch(command, entry.pattern)


def match_exec_allowlist(command: str, entries: list[ExecAllowlistEntry]) -> bool:
    return any(match_exec_allowlist_entry(command, e) for e in entries)


# ─── exec-approvals.ts ───

@dataclass
class ExecApprovalRequest:
    command: str = ""
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    env: dict[str, str] | None = None
    run_id: str | None = None
    tool_call_id: str | None = None


@dataclass
class ExecApprovalResult:
    approved: bool = False
    reason: str = ""
    modified_command: str | None = None
    modified_args: list[str] | None = None


ExecApprovalPolicy = Literal["auto", "prompt", "deny", "allowlist"]


def resolve_exec_approval_policy(command: str, allowlist: list[ExecAllowlistEntry] | None = None,
                                  policy: ExecApprovalPolicy = "prompt") -> ExecApprovalResult:
    if policy == "auto":
        return ExecApprovalResult(approved=True, reason="auto")
    if policy == "deny":
        return ExecApprovalResult(approved=False, reason="deny")
    if policy == "allowlist" and allowlist:
        if match_exec_allowlist(command, allowlist):
            return ExecApprovalResult(approved=True, reason="allowlist")
        return ExecApprovalResult(approved=False, reason="not in allowlist")
    return ExecApprovalResult(approved=False, reason="prompt")


# ─── exec-command-resolution.ts ───

def resolve_command_path(command: str) -> str | None:
    return shutil.which(command)


def is_command_available(command: str) -> bool:
    return resolve_command_path(command) is not None


# ─── exec-obfuscation-detect.ts ───

_OBFUSCATION_PATTERNS = [
    re.compile(r'\$\{IFS\}'),
    re.compile(r'\$\(echo'),
    re.compile(r'\\x[0-9a-fA-F]{2}'),
    re.compile(r'base64\s+(-d|--decode)'),
    re.compile(r'\$\(\(.*\)\)'),
    re.compile(r'eval\s+'),
    re.compile(r"\\[0-7]{3}"),
    re.compile(r"\\u[0-9a-fA-F]{4}"),
]


def detect_command_obfuscation(command: str) -> list[str]:
    findings: list[str] = []
    for pattern in _OBFUSCATION_PATTERNS:
        if pattern.search(command):
            findings.append(f"obfuscation pattern: {pattern.pattern}")
    return findings


def is_command_obfuscated(command: str) -> bool:
    return bool(detect_command_obfuscation(command))


# ─── exec-safe-bin-policy.ts ───

@dataclass
class SafeBinPolicy:
    name: str = ""
    allowed_commands: list[str] = field(default_factory=list)
    blocked_commands: list[str] = field(default_factory=list)
    blocked_args: list[str] = field(default_factory=list)
    blocked_flags: list[str] = field(default_factory=list)
    allow_network: bool = False
    allow_write: bool = False
    allow_exec: bool = False
    max_runtime_ms: int = 30_000


SAFE_BIN_POLICY_PROFILES: dict[str, SafeBinPolicy] = {
    "read-only": SafeBinPolicy(
        name="read-only",
        allowed_commands=["cat", "ls", "head", "tail", "wc", "grep", "find", "file", "stat", "du", "df", "tree"],
        blocked_commands=["rm", "mv", "cp", "dd", "mkfs", "fdisk"],
        allow_network=False, allow_write=False, allow_exec=False,
    ),
    "standard": SafeBinPolicy(
        name="standard",
        blocked_commands=["rm -rf /", "mkfs", "fdisk", "dd if=/dev"],
        blocked_flags=["--no-preserve-root"],
        allow_network=True, allow_write=True, allow_exec=True,
    ),
}


def evaluate_safe_bin_policy(command: str, args: list[str] | None = None, policy: SafeBinPolicy | None = None) -> ExecApprovalResult:
    if not policy:
        return ExecApprovalResult(approved=True, reason="no policy")
    if policy.allowed_commands and command not in policy.allowed_commands:
        return ExecApprovalResult(approved=False, reason=f"command '{command}' not in allowed list")
    if command in policy.blocked_commands:
        return ExecApprovalResult(approved=False, reason=f"command '{command}' is blocked")
    if args and policy.blocked_flags:
        for arg in args:
            if arg in policy.blocked_flags:
                return ExecApprovalResult(approved=False, reason=f"flag '{arg}' is blocked")
    return ExecApprovalResult(approved=True, reason="policy passed")


# ─── exec-safety.ts ───

def is_safe_exec_command(command: str, args: list[str] | None = None) -> bool:
    if is_command_obfuscated(command):
        return False
    full = f"{command} {' '.join(args or [])}"
    dangerous = ["rm -rf /", "mkfs", "fdisk /dev", ":(){:|:&};:", "dd if=/dev/zero of=/dev"]
    return not any(d in full for d in dangerous)


# ─── exec-host.ts ───

@dataclass
class ExecHostResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    killed: bool = False
    timed_out: bool = False
    duration_ms: int = 0


async def exec_host_command(command: str, args: list[str] | None = None, cwd: str | None = None,
                             env: dict[str, str] | None = None, timeout_ms: int = 30000,
                             stdin: str | None = None) -> ExecHostResult:
    import asyncio
    cmd_args = [command] + (args or [])
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_args, cwd=cwd, env={**os.environ, **(env or {})},
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin else None,
        )
        start = time.time()
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=stdin.encode() if stdin else None),
                timeout=timeout_ms / 1000.0,
            )
            duration = int((time.time() - start) * 1000)
            return ExecHostResult(
                stdout=stdout_bytes.decode(errors="replace"),
                stderr=stderr_bytes.decode(errors="replace"),
                exit_code=proc.returncode or 0,
                duration_ms=duration,
            )
        except asyncio.TimeoutError:
            proc.kill()
            duration = int((time.time() - start) * 1000)
            return ExecHostResult(exit_code=-1, killed=True, timed_out=True, duration_ms=duration)
    except FileNotFoundError:
        return ExecHostResult(exit_code=127, stderr=f"command not found: {command}")
    except Exception as e:
        return ExecHostResult(exit_code=-1, stderr=str(e))


import time

# ─── exec-wrapper-resolution.ts ───

def resolve_exec_wrapper(command: str) -> str | None:
    """Resolve wrapper scripts like npx, bunx etc."""
    wrappers = {"npx": "npx", "bunx": "bunx", "pnpx": "pnpx", "yarn": "yarn"}
    base = os.path.basename(command).lower().split(".")[0]
    return wrappers.get(base)


# ─── exec-approval-forwarder.ts ───

_approval_forwarder: Callable[..., Any] | None = None


def set_exec_approval_forwarder(handler: Callable[..., Any] | None) -> None:
    global _approval_forwarder
    _approval_forwarder = handler


def get_exec_approval_forwarder() -> Callable[..., Any] | None:
    return _approval_forwarder


# ─── executable-path.ts ───

def resolve_executable_path(name: str, search_paths: list[str] | None = None) -> str | None:
    if search_paths:
        for directory in search_paths:
            candidate = os.path.join(directory, name)
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
    return shutil.which(name)


# ─── exec-approvals.ts: full approvals system ───

import hashlib
import json
import logging
import time
import uuid

logger = logging.getLogger("infra.exec_safety")

ExecHost = Literal["sandbox", "gateway", "node"]
ExecSecurity = Literal["deny", "allowlist", "full"]
ExecAsk = Literal["off", "on-miss", "always"]
ExecApprovalDecision = Literal["allow-once", "allow-always", "deny"]

DEFAULT_AGENT_ID = "main"
DEFAULT_EXEC_APPROVAL_TIMEOUT_MS = 120_000
_DEFAULT_SECURITY: ExecSecurity = "deny"
_DEFAULT_ASK: ExecAsk = "on-miss"
_DEFAULT_ASK_FALLBACK: ExecSecurity = "deny"
_DEFAULT_AUTO_ALLOW_SKILLS = False
_DEFAULT_SOCKET = "~/.openclaw/exec-approvals.sock"
_DEFAULT_FILE = "~/.openclaw/exec-approvals.json"


def _expand_home(p: str) -> str:
    if p.startswith("~/"):
        return os.path.join(os.path.expanduser("~"), p[2:])
    return p


def normalize_exec_host(value: str | None) -> ExecHost | None:
    if not value:
        return None
    v = value.strip().lower()
    if v in ("sandbox", "gateway", "node"):
        return v  # type: ignore
    return None


def normalize_exec_security(value: str | None) -> ExecSecurity | None:
    if not value:
        return None
    v = value.strip().lower()
    if v in ("deny", "allowlist", "full"):
        return v  # type: ignore
    return None


def normalize_exec_ask(value: str | None) -> ExecAsk | None:
    if not value:
        return None
    v = value.strip().lower()
    if v in ("off", "on-miss", "always"):
        return v  # type: ignore
    return None


@dataclass
class ExecApprovalRequestPayload:
    command: str = ""
    command_argv: list[str] | None = None
    env_keys: list[str] | None = None
    cwd: str | None = None
    node_id: str | None = None
    host: str | None = None
    security: str | None = None
    ask: str | None = None
    agent_id: str | None = None
    resolved_path: str | None = None
    session_key: str | None = None


@dataclass
class ExecApprovalRequestFull:
    id: str = ""
    request: ExecApprovalRequestPayload = field(default_factory=ExecApprovalRequestPayload)
    created_at_ms: float = 0.0
    expires_at_ms: float = 0.0


@dataclass
class ExecApprovalResolved:
    id: str = ""
    decision: str = ""  # ExecApprovalDecision
    resolved_by: str | None = None
    ts: float = 0.0
    request: ExecApprovalRequestPayload | None = None


@dataclass
class ExecApprovalsDefaults:
    security: ExecSecurity | None = None
    ask: ExecAsk | None = None
    ask_fallback: ExecSecurity | None = None
    auto_allow_skills: bool | None = None


@dataclass
class ExecAllowlistEntryFull:
    id: str | None = None
    pattern: str = ""
    last_used_at: float | None = None
    last_used_command: str | None = None
    last_resolved_path: str | None = None


@dataclass
class ExecApprovalsAgent:
    security: ExecSecurity | None = None
    ask: ExecAsk | None = None
    ask_fallback: ExecSecurity | None = None
    auto_allow_skills: bool | None = None
    allowlist: list[ExecAllowlistEntryFull] | None = None


@dataclass
class ExecApprovalsFile:
    version: int = 1
    socket: dict[str, str | None] | None = None
    defaults: ExecApprovalsDefaults | None = None
    agents: dict[str, ExecApprovalsAgent] | None = None


@dataclass
class ExecApprovalsSnapshot:
    path: str = ""
    exists: bool = False
    raw: str | None = None
    file: ExecApprovalsFile = field(default_factory=ExecApprovalsFile)
    hash: str = ""


@dataclass
class ExecApprovalsResolvedFull:
    path: str = ""
    socket_path: str = ""
    token: str = ""
    defaults: ExecApprovalsDefaults = field(default_factory=ExecApprovalsDefaults)
    agent: ExecApprovalsDefaults = field(default_factory=ExecApprovalsDefaults)
    allowlist: list[ExecAllowlistEntryFull] = field(default_factory=list)
    file: ExecApprovalsFile = field(default_factory=ExecApprovalsFile)


def resolve_exec_approvals_path() -> str:
    return _expand_home(_DEFAULT_FILE)


def resolve_exec_approvals_socket_path() -> str:
    return _expand_home(_DEFAULT_SOCKET)


def _hash_raw(raw: str | None) -> str:
    return hashlib.sha256((raw or "").encode()).hexdigest()


def _coerce_allowlist_entries(allowlist: Any) -> list[ExecAllowlistEntryFull] | None:
    """Coerce legacy/corrupted allowlists into proper entry objects."""
    if not isinstance(allowlist, list):
        return None
    if not allowlist:
        return []
    result: list[ExecAllowlistEntryFull] = []
    for item in allowlist:
        if isinstance(item, str):
            trimmed = item.strip()
            if trimmed:
                result.append(ExecAllowlistEntryFull(pattern=trimmed))
        elif isinstance(item, dict):
            pattern = item.get("pattern", "")
            if isinstance(pattern, str) and pattern.strip():
                result.append(ExecAllowlistEntryFull(
                    id=item.get("id"),
                    pattern=pattern.strip(),
                    last_used_at=item.get("lastUsedAt"),
                    last_used_command=item.get("lastUsedCommand"),
                    last_resolved_path=item.get("lastResolvedPath"),
                ))
    return result if result else None


def _ensure_allowlist_ids(allowlist: list[ExecAllowlistEntryFull] | None) -> list[ExecAllowlistEntryFull] | None:
    if not allowlist:
        return allowlist
    changed = False
    result = []
    for entry in allowlist:
        if entry.id:
            result.append(entry)
        else:
            changed = True
            result.append(ExecAllowlistEntryFull(
                id=str(uuid.uuid4()), pattern=entry.pattern,
                last_used_at=entry.last_used_at, last_used_command=entry.last_used_command,
                last_resolved_path=entry.last_resolved_path,
            ))
    return result if changed else allowlist


def _merge_legacy_agent(current: ExecApprovalsAgent, legacy: ExecApprovalsAgent) -> ExecApprovalsAgent:
    """Merge legacy 'default' agent into current."""
    seen: set[str] = set()
    merged: list[ExecAllowlistEntryFull] = []
    for entries in [current.allowlist or [], legacy.allowlist or []]:
        for entry in entries:
            key = entry.pattern.strip().lower()
            if key and key not in seen:
                seen.add(key)
                merged.append(entry)
    return ExecApprovalsAgent(
        security=current.security or legacy.security,
        ask=current.ask or legacy.ask,
        ask_fallback=current.ask_fallback or legacy.ask_fallback,
        auto_allow_skills=current.auto_allow_skills if current.auto_allow_skills is not None else legacy.auto_allow_skills,
        allowlist=merged if merged else None,
    )


def normalize_exec_approvals(file: ExecApprovalsFile) -> ExecApprovalsFile:
    """Normalize an exec approvals file structure."""
    socket_path = (file.socket or {}).get("path", "")
    token = (file.socket or {}).get("token", "")
    agents = dict(file.agents or {})

    # Merge legacy 'default' agent
    legacy = agents.pop("default", None)
    if legacy:
        main = agents.get(DEFAULT_AGENT_ID)
        agents[DEFAULT_AGENT_ID] = _merge_legacy_agent(main, legacy) if main else legacy

    for key, agent in list(agents.items()):
        coerced = _coerce_allowlist_entries(
            [{"id": e.id, "pattern": e.pattern, "lastUsedAt": e.last_used_at,
              "lastUsedCommand": e.last_used_command, "lastResolvedPath": e.last_resolved_path}
             for e in agent.allowlist] if agent.allowlist else None
        )
        updated = _ensure_allowlist_ids(coerced)
        if updated is not agent.allowlist:
            agents[key] = ExecApprovalsAgent(
                security=agent.security, ask=agent.ask,
                ask_fallback=agent.ask_fallback, auto_allow_skills=agent.auto_allow_skills,
                allowlist=updated,
            )

    return ExecApprovalsFile(
        version=1,
        socket={"path": socket_path.strip() if socket_path else None,
                "token": token.strip() if token else None},
        defaults=ExecApprovalsDefaults(
            security=file.defaults.security if file.defaults else None,
            ask=file.defaults.ask if file.defaults else None,
            ask_fallback=file.defaults.ask_fallback if file.defaults else None,
            auto_allow_skills=file.defaults.auto_allow_skills if file.defaults else None,
        ),
        agents=agents,
    )


def _parse_exec_approvals_file(data: dict[str, Any]) -> ExecApprovalsFile:
    """Parse raw JSON dict into ExecApprovalsFile."""
    defaults_raw = data.get("defaults") or {}
    agents_raw = data.get("agents") or {}
    agents: dict[str, ExecApprovalsAgent] = {}
    for key, agent_data in agents_raw.items():
        if not isinstance(agent_data, dict):
            continue
        allowlist_raw = agent_data.get("allowlist")
        allowlist = None
        if isinstance(allowlist_raw, list):
            allowlist = []
            for item in allowlist_raw:
                if isinstance(item, str):
                    if item.strip():
                        allowlist.append(ExecAllowlistEntryFull(pattern=item.strip()))
                elif isinstance(item, dict):
                    pattern = item.get("pattern", "")
                    if isinstance(pattern, str) and pattern.strip():
                        allowlist.append(ExecAllowlistEntryFull(
                            id=item.get("id"), pattern=pattern.strip(),
                            last_used_at=item.get("lastUsedAt"),
                            last_used_command=item.get("lastUsedCommand"),
                            last_resolved_path=item.get("lastResolvedPath"),
                        ))
        agents[key] = ExecApprovalsAgent(
            security=normalize_exec_security(agent_data.get("security")),
            ask=normalize_exec_ask(agent_data.get("ask")),
            ask_fallback=normalize_exec_security(agent_data.get("askFallback")),
            auto_allow_skills=agent_data.get("autoAllowSkills"),
            allowlist=allowlist,
        )
    return ExecApprovalsFile(
        version=data.get("version", 1),
        socket=data.get("socket"),
        defaults=ExecApprovalsDefaults(
            security=normalize_exec_security(defaults_raw.get("security")),
            ask=normalize_exec_ask(defaults_raw.get("ask")),
            ask_fallback=normalize_exec_security(defaults_raw.get("askFallback")),
            auto_allow_skills=defaults_raw.get("autoAllowSkills"),
        ),
        agents=agents,
    )


def load_exec_approvals() -> ExecApprovalsFile:
    """Load exec approvals from the default file path."""
    file_path = resolve_exec_approvals_path()
    try:
        if not os.path.isfile(file_path):
            return normalize_exec_approvals(ExecApprovalsFile())
        with open(file_path, "r") as f:
            parsed = json.load(f)
        if not isinstance(parsed, dict) or parsed.get("version") != 1:
            return normalize_exec_approvals(ExecApprovalsFile())
        return normalize_exec_approvals(_parse_exec_approvals_file(parsed))
    except Exception:
        return normalize_exec_approvals(ExecApprovalsFile())


def read_exec_approvals_snapshot() -> ExecApprovalsSnapshot:
    """Read exec approvals file with hash for change detection."""
    file_path = resolve_exec_approvals_path()
    if not os.path.isfile(file_path):
        file = normalize_exec_approvals(ExecApprovalsFile())
        return ExecApprovalsSnapshot(
            path=file_path, exists=False, raw=None,
            file=file, hash=_hash_raw(None),
        )
    try:
        with open(file_path, "r") as f:
            raw = f.read()
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and parsed.get("version") == 1:
            file = normalize_exec_approvals(_parse_exec_approvals_file(parsed))
        else:
            file = normalize_exec_approvals(ExecApprovalsFile())
        return ExecApprovalsSnapshot(
            path=file_path, exists=True, raw=raw,
            file=file, hash=_hash_raw(raw),
        )
    except Exception:
        file = normalize_exec_approvals(ExecApprovalsFile())
        return ExecApprovalsSnapshot(
            path=file_path, exists=True, raw=None,
            file=file, hash=_hash_raw(None),
        )


def _serialize_exec_approvals(file: ExecApprovalsFile) -> dict[str, Any]:
    """Serialize an ExecApprovalsFile to JSON-safe dict."""
    agents: dict[str, Any] = {}
    for key, agent in (file.agents or {}).items():
        agent_data: dict[str, Any] = {}
        if agent.security:
            agent_data["security"] = agent.security
        if agent.ask:
            agent_data["ask"] = agent.ask
        if agent.ask_fallback:
            agent_data["askFallback"] = agent.ask_fallback
        if agent.auto_allow_skills is not None:
            agent_data["autoAllowSkills"] = agent.auto_allow_skills
        if agent.allowlist:
            agent_data["allowlist"] = [
                {k: v for k, v in {
                    "id": e.id, "pattern": e.pattern,
                    "lastUsedAt": e.last_used_at,
                    "lastUsedCommand": e.last_used_command,
                    "lastResolvedPath": e.last_resolved_path,
                }.items() if v is not None}
                for e in agent.allowlist
            ]
        agents[key] = agent_data

    result: dict[str, Any] = {"version": 1}
    if file.socket:
        result["socket"] = {k: v for k, v in file.socket.items() if v}
    if file.defaults:
        defs: dict[str, Any] = {}
        if file.defaults.security:
            defs["security"] = file.defaults.security
        if file.defaults.ask:
            defs["ask"] = file.defaults.ask
        if file.defaults.ask_fallback:
            defs["askFallback"] = file.defaults.ask_fallback
        if file.defaults.auto_allow_skills is not None:
            defs["autoAllowSkills"] = file.defaults.auto_allow_skills
        if defs:
            result["defaults"] = defs
    if agents:
        result["agents"] = agents
    return result


def save_exec_approvals(file: ExecApprovalsFile) -> None:
    """Save exec approvals to the default file path."""
    file_path = resolve_exec_approvals_path()
    parent = os.path.dirname(file_path)
    os.makedirs(parent, exist_ok=True)
    data = _serialize_exec_approvals(file)
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    try:
        os.chmod(file_path, 0o600)
    except OSError:
        pass


def _generate_token() -> str:
    return uuid.uuid4().hex[:32]


def ensure_exec_approvals() -> ExecApprovalsFile:
    """Ensure exec approvals file exists and has valid socket config."""
    loaded = load_exec_approvals()
    normalized = normalize_exec_approvals(loaded)
    socket = normalized.socket or {}
    socket_path = (socket.get("path") or "").strip()
    token = (socket.get("token") or "").strip()
    updated = ExecApprovalsFile(
        version=1,
        socket={
            "path": socket_path if socket_path else resolve_exec_approvals_socket_path(),
            "token": token if token else _generate_token(),
        },
        defaults=normalized.defaults,
        agents=normalized.agents,
    )
    save_exec_approvals(updated)
    return updated


def _normalize_security(value: ExecSecurity | None, fallback: ExecSecurity) -> ExecSecurity:
    if value in ("allowlist", "full", "deny"):
        return value  # type: ignore
    return fallback


def _normalize_ask(value: ExecAsk | None, fallback: ExecAsk) -> ExecAsk:
    if value in ("always", "off", "on-miss"):
        return value  # type: ignore
    return fallback


def resolve_exec_approvals_full(
    agent_id: str | None = None,
    overrides: dict[str, Any] | None = None,
) -> ExecApprovalsResolvedFull:
    """Resolve exec approvals for an agent with defaults and overrides."""
    file = ensure_exec_approvals()
    defaults = file.defaults or ExecApprovalsDefaults()
    agent_key = agent_id or DEFAULT_AGENT_ID
    agent = (file.agents or {}).get(agent_key, ExecApprovalsAgent())
    wildcard = (file.agents or {}).get("*", ExecApprovalsAgent())
    overrides = overrides or {}

    fallback_security = overrides.get("security") or _DEFAULT_SECURITY
    fallback_ask = overrides.get("ask") or _DEFAULT_ASK
    fallback_ask_fallback = overrides.get("ask_fallback") or _DEFAULT_ASK_FALLBACK
    fallback_auto_allow = overrides.get("auto_allow_skills", _DEFAULT_AUTO_ALLOW_SKILLS)

    resolved_defaults = ExecApprovalsDefaults(
        security=_normalize_security(defaults.security, fallback_security),
        ask=_normalize_ask(defaults.ask, fallback_ask),
        ask_fallback=_normalize_security(defaults.ask_fallback or fallback_ask_fallback, fallback_ask_fallback),
        auto_allow_skills=bool(defaults.auto_allow_skills if defaults.auto_allow_skills is not None else fallback_auto_allow),
    )
    resolved_agent = ExecApprovalsDefaults(
        security=_normalize_security(
            agent.security or wildcard.security or resolved_defaults.security,
            resolved_defaults.security),
        ask=_normalize_ask(
            agent.ask or wildcard.ask or resolved_defaults.ask,
            resolved_defaults.ask),
        ask_fallback=_normalize_security(
            agent.ask_fallback or wildcard.ask_fallback or resolved_defaults.ask_fallback,
            resolved_defaults.ask_fallback),
        auto_allow_skills=bool(
            agent.auto_allow_skills if agent.auto_allow_skills is not None
            else wildcard.auto_allow_skills if wildcard.auto_allow_skills is not None
            else resolved_defaults.auto_allow_skills),
    )
    allowlist = list(wildcard.allowlist or []) + list(agent.allowlist or [])
    socket = file.socket or {}

    return ExecApprovalsResolvedFull(
        path=resolve_exec_approvals_path(),
        socket_path=_expand_home(socket.get("path") or resolve_exec_approvals_socket_path()),
        token=socket.get("token") or "",
        defaults=resolved_defaults,
        agent=resolved_agent,
        allowlist=allowlist,
        file=file,
    )


def requires_exec_approval(ask: str, security: str, analysis_ok: bool, allowlist_satisfied: bool) -> bool:
    """Determine if exec approval is required."""
    return (
        ask == "always"
        or (ask == "on-miss" and security == "allowlist"
            and (not analysis_ok or not allowlist_satisfied))
    )


def record_allowlist_use(
    approvals: ExecApprovalsFile,
    agent_id: str | None,
    entry: ExecAllowlistEntryFull,
    command: str,
    resolved_path: str | None = None,
) -> None:
    """Record usage of an allowlist entry."""
    target = agent_id or DEFAULT_AGENT_ID
    agents = approvals.agents or {}
    existing = agents.get(target, ExecApprovalsAgent())
    allowlist = list(existing.allowlist or [])
    now = time.time() * 1000
    updated = []
    for item in allowlist:
        if item.pattern == entry.pattern:
            updated.append(ExecAllowlistEntryFull(
                id=item.id or str(uuid.uuid4()),
                pattern=item.pattern,
                last_used_at=now,
                last_used_command=command,
                last_resolved_path=resolved_path,
            ))
        else:
            updated.append(item)
    agents[target] = ExecApprovalsAgent(
        security=existing.security, ask=existing.ask,
        ask_fallback=existing.ask_fallback, auto_allow_skills=existing.auto_allow_skills,
        allowlist=updated,
    )
    approvals.agents = agents
    save_exec_approvals(approvals)


def add_allowlist_entry(
    approvals: ExecApprovalsFile,
    agent_id: str | None,
    pattern: str,
) -> None:
    """Add a new pattern to the allowlist."""
    trimmed = pattern.strip()
    if not trimmed:
        return
    target = agent_id or DEFAULT_AGENT_ID
    agents = approvals.agents or {}
    existing = agents.get(target, ExecApprovalsAgent())
    allowlist = list(existing.allowlist or [])
    if any(e.pattern == trimmed for e in allowlist):
        return
    allowlist.append(ExecAllowlistEntryFull(
        id=str(uuid.uuid4()), pattern=trimmed,
        last_used_at=time.time() * 1000,
    ))
    agents[target] = ExecApprovalsAgent(
        security=existing.security, ask=existing.ask,
        ask_fallback=existing.ask_fallback, auto_allow_skills=existing.auto_allow_skills,
        allowlist=allowlist,
    )
    approvals.agents = agents
    save_exec_approvals(approvals)


def min_security(a: str, b: str) -> str:
    """Return the more restrictive of two security levels."""
    order = {"deny": 0, "allowlist": 1, "full": 2}
    return a if order.get(a, 0) <= order.get(b, 0) else b


def max_ask(a: str, b: str) -> str:
    """Return the less restrictive of two ask levels."""
    order = {"off": 0, "on-miss": 1, "always": 2}
    return a if order.get(a, 0) >= order.get(b, 0) else b


# ─── exec-approvals-allowlist.ts: shell command analysis ───

def normalize_safe_bins(entries: list[str] | None = None) -> set[str]:
    if not entries:
        return set()
    return {e.strip().lower() for e in entries if e.strip()}


DEFAULT_SAFE_BINS = [
    "cat", "ls", "head", "tail", "wc", "grep", "find", "file", "stat",
    "du", "df", "tree", "echo", "printf", "date", "whoami", "hostname",
    "uname", "pwd", "env", "sort", "uniq", "cut", "tr", "sed", "awk",
    "diff", "tee", "basename", "dirname", "realpath", "readlink",
    "which", "type", "test", "true", "false",
]


def resolve_safe_bins(entries: list[str] | None = None) -> set[str]:
    if entries is None:
        return normalize_safe_bins(DEFAULT_SAFE_BINS)
    return normalize_safe_bins(entries)


@dataclass
class ExecCommandSegment:
    raw: str = ""
    argv: list[str] = field(default_factory=list)
    resolution: dict[str, Any] | None = None


@dataclass
class ExecCommandAnalysis:
    ok: bool = True
    segments: list[ExecCommandSegment] = field(default_factory=list)
    chains: list[list[ExecCommandSegment]] | None = None


@dataclass
class ExecAllowlistEvaluation:
    allowlist_satisfied: bool = False
    allowlist_matches: list[ExecAllowlistEntryFull] = field(default_factory=list)
    segment_satisfied_by: list[str | None] = field(default_factory=list)


def match_allowlist_pattern(pattern: str, command: str) -> bool:
    """Match a command against an allowlist pattern."""
    pat = pattern.strip().lower()
    cmd = command.strip().lower()
    if not pat or not cmd:
        return False
    return fnmatch.fnmatch(cmd, pat) or cmd == pat or cmd.endswith("/" + pat)


def match_allowlist(
    allowlist: list[ExecAllowlistEntryFull],
    resolution: dict[str, Any] | None,
) -> ExecAllowlistEntryFull | None:
    """Check if a command resolution matches any allowlist entry."""
    if not resolution or not allowlist:
        return None
    candidates = [
        resolution.get("resolvedPath", ""),
        resolution.get("rawExecutable", ""),
        resolution.get("executableName", ""),
    ]
    for entry in allowlist:
        for candidate in candidates:
            if candidate and match_allowlist_pattern(entry.pattern, candidate):
                return entry
    return None


def evaluate_exec_allowlist(
    analysis: ExecCommandAnalysis,
    allowlist: list[ExecAllowlistEntryFull],
    safe_bins: set[str] | None = None,
) -> ExecAllowlistEvaluation:
    """Evaluate whether a shell command analysis is covered by the allowlist."""
    if not analysis.ok or not analysis.segments:
        return ExecAllowlistEvaluation()

    all_matches: list[ExecAllowlistEntryFull] = []
    segment_satisfied: list[str | None] = []
    safe = safe_bins or set()

    for segment in analysis.segments:
        resolution = segment.resolution
        match = match_allowlist(allowlist, resolution)
        if match:
            all_matches.append(match)
            segment_satisfied.append("allowlist")
            continue
        # Check safe bins
        exec_name = (resolution or {}).get("executableName", "").lower()
        if exec_name and exec_name in safe:
            segment_satisfied.append("safeBins")
            continue
        segment_satisfied.append(None)

    all_satisfied = all(s is not None for s in segment_satisfied)
    return ExecAllowlistEvaluation(
        allowlist_satisfied=all_satisfied,
        allowlist_matches=all_matches,
        segment_satisfied_by=segment_satisfied,
    )
