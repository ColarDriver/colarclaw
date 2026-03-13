"""Infra system run — ported from bk/src/infra/system-run-command.ts,
system-run-approval-binding.ts, system-run-approval-context.ts,
system-run-normalize.ts, system-message.ts, system-presence.ts,
runtime-guard.ts, runtime-status.ts.

System command execution with approval flow, system messages,
presence detection, runtime guards.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

logger = logging.getLogger("infra.system_run")


# ─── system-run-normalize.ts ───

def normalize_run_command(command: str) -> str:
    """Normalize a command string for comparison."""
    return re.sub(r"\s+", " ", command.strip())


# ─── system-run-approval-context.ts ───

@dataclass
class RunApprovalContext:
    command: str = ""
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    run_id: str | None = None
    tool_call_id: str | None = None
    session_key: str | None = None
    is_auto_approved: bool = False
    approval_source: str = ""  # "user" | "allowlist" | "safe-bin" | "auto"


# ─── system-run-approval-binding.ts ───

_approval_binding: Callable[..., Any] | None = None


def set_system_run_approval_binding(handler: Callable[..., Any] | None) -> None:
    global _approval_binding
    _approval_binding = handler


def get_system_run_approval_binding() -> Callable[..., Any] | None:
    return _approval_binding


@dataclass
class SystemRunApprovalRequest:
    command: str = ""
    args: list[str] = field(default_factory=list)
    cwd: str | None = None
    run_id: str | None = None
    tool_call_id: str | None = None


@dataclass
class SystemRunApprovalResult:
    approved: bool = False
    reason: str = ""
    modified_command: str | None = None


async def request_system_run_approval(request: SystemRunApprovalRequest) -> SystemRunApprovalResult:
    """Request approval for a system command execution."""
    if _approval_binding:
        try:
            result = _approval_binding(request)
            if asyncio.iscoroutine(result):
                result = await result
            if isinstance(result, SystemRunApprovalResult):
                return result
            if isinstance(result, dict):
                return SystemRunApprovalResult(**result)
        except Exception as e:
            return SystemRunApprovalResult(approved=False, reason=f"approval error: {e}")
    return SystemRunApprovalResult(approved=False, reason="no approval binding")


# ─── system-run-command.ts: command validation and resolution ───

import hashlib

POSIX_SHELLS = {"ash", "bash", "dash", "fish", "ksh", "sh", "zsh"}
POWERSHELL_SHELLS = {"powershell", "pwsh"}
ALL_SHELL_WRAPPERS = POSIX_SHELLS | POWERSHELL_SHELLS

POSIX_INLINE_FLAGS = {"-c"}
POWERSHELL_INLINE_FLAGS = {"-command", "-c"}


def format_exec_command(argv: list[str]) -> str:
    """Format argv into a display-safe command string."""
    parts = []
    for arg in argv:
        if not arg:
            parts.append('""')
        elif re.search(r'\s|"', arg):
            parts.append(f'"{arg.replace(chr(34), chr(92)+chr(34))}"')
        else:
            parts.append(arg)
    return " ".join(parts)


def _normalize_executable_token(token: str) -> str:
    """Normalize a shell executable token (strip path, extension)."""
    name = os.path.basename(token).strip()
    # Strip common extensions
    for ext in (".exe", ".cmd", ".bat"):
        if name.lower().endswith(ext):
            name = name[:-len(ext)]
            break
    return name.lower()


def extract_shell_command_from_argv(argv: list[str]) -> str | None:
    """Extract the inline command from a shell wrapper argv like ['bash', '-c', 'echo hi']."""
    if len(argv) < 3:
        return None
    wrapper = _normalize_executable_token(argv[0])
    if wrapper not in ALL_SHELL_WRAPPERS:
        return None
    inline_flags = POWERSHELL_INLINE_FLAGS if wrapper in POWERSHELL_SHELLS else POSIX_INLINE_FLAGS
    for i, arg in enumerate(argv[1:], 1):
        if arg.strip().lower() in inline_flags:
            if i + 1 < len(argv):
                return argv[i + 1]
            return None
        # Combined -c flag (e.g. "-xc")
        if wrapper in POSIX_SHELLS and len(arg) > 2 and arg.startswith("-") and arg.endswith("c"):
            if i + 1 < len(argv):
                return argv[i + 1]
            return None
    return None


def _has_trailing_positional_after_inline(argv: list[str]) -> bool:
    """Check if there are trailing positional args after the inline command."""
    if len(argv) < 3:
        return False
    wrapper = _normalize_executable_token(argv[0])
    if wrapper not in ALL_SHELL_WRAPPERS:
        return False
    inline_flags = POWERSHELL_INLINE_FLAGS if wrapper in POWERSHELL_SHELLS else POSIX_INLINE_FLAGS
    for i, arg in enumerate(argv[1:], 1):
        if arg.strip().lower() in inline_flags:
            # The inline command value is at i+1, anything after is trailing
            return any(a.strip() for a in argv[i + 2:]) if i + 2 < len(argv) else False
        if wrapper in POSIX_SHELLS and len(arg) > 2 and arg.startswith("-") and arg.endswith("c"):
            return any(a.strip() for a in argv[i + 2:]) if i + 2 < len(argv) else False
    return False


@dataclass
class SystemRunCommandValidation:
    ok: bool = True
    shell_command: str | None = None
    cmd_text: str = ""
    message: str = ""
    details: dict[str, Any] | None = None


def validate_system_run_command(
    argv: list[str],
    raw_command: str | None = None,
) -> SystemRunCommandValidation:
    """Validate and resolve display text / shell command from an argv."""
    raw = raw_command.strip() if raw_command and raw_command.strip() else None
    shell_command = extract_shell_command_from_argv(argv)
    trailing = _has_trailing_positional_after_inline(argv)
    must_bind_display_to_full_argv = trailing

    if shell_command is not None and not must_bind_display_to_full_argv:
        inferred = shell_command.strip()
    else:
        inferred = format_exec_command(argv)

    if raw and raw != inferred:
        return SystemRunCommandValidation(
            ok=False,
            message="INVALID_REQUEST: rawCommand does not match command",
            details={"code": "RAW_COMMAND_MISMATCH", "rawCommand": raw, "inferred": inferred},
        )

    return SystemRunCommandValidation(
        ok=True,
        shell_command=raw or shell_command if shell_command is not None else None,
        cmd_text=raw or inferred,
    )


@dataclass
class ResolvedSystemRunCommand:
    ok: bool = True
    argv: list[str] = field(default_factory=list)
    raw_command: str | None = None
    shell_command: str | None = None
    cmd_text: str = ""
    message: str = ""
    details: dict[str, Any] | None = None


def resolve_system_run_command(
    command: Any = None,
    raw_command: Any = None,
) -> ResolvedSystemRunCommand:
    """Resolve a system run command from tool call parameters."""
    raw = raw_command.strip() if isinstance(raw_command, str) and raw_command.strip() else None
    cmd_list = command if isinstance(command, list) else []
    if not cmd_list:
        if raw:
            return ResolvedSystemRunCommand(
                ok=False,
                message="rawCommand requires params.command",
                details={"code": "MISSING_COMMAND"},
            )
        return ResolvedSystemRunCommand(ok=True)

    argv = [str(v) for v in cmd_list]
    validation = validate_system_run_command(argv, raw)
    if not validation.ok:
        return ResolvedSystemRunCommand(
            ok=False, message=validation.message, details=validation.details,
        )
    return ResolvedSystemRunCommand(
        ok=True, argv=argv, raw_command=raw,
        shell_command=validation.shell_command, cmd_text=validation.cmd_text,
    )


# ─── system-run-approval-binding.ts: binding match logic ───

def normalize_non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed if trimmed else None


def normalize_string_array(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(v).strip() for v in value if isinstance(v, str) and v.strip()]


@dataclass
class SystemRunApprovalFileOperand:
    argv_index: int = 0
    path: str = ""
    sha256: str = ""


@dataclass
class SystemRunApprovalPlan:
    argv: list[str] = field(default_factory=list)
    cwd: str | None = None
    raw_command: str | None = None
    agent_id: str | None = None
    session_key: str | None = None
    mutable_file_operand: SystemRunApprovalFileOperand | None = None


def normalize_system_run_approval_plan(value: Any) -> SystemRunApprovalPlan | None:
    """Normalize a raw approval plan payload into a structured plan."""
    if not value or not isinstance(value, dict):
        return None
    argv = normalize_string_array(value.get("argv"))
    if not argv:
        return None
    mfo_raw = value.get("mutableFileOperand")
    mfo = None
    if isinstance(mfo_raw, dict):
        idx = mfo_raw.get("argvIndex")
        path = normalize_non_empty_string(mfo_raw.get("path"))
        sha = normalize_non_empty_string(mfo_raw.get("sha256"))
        if isinstance(idx, int) and idx >= 0 and path and sha:
            mfo = SystemRunApprovalFileOperand(argv_index=idx, path=path, sha256=sha)
        elif mfo_raw:
            return None  # invalid mutableFileOperand
    return SystemRunApprovalPlan(
        argv=argv,
        cwd=normalize_non_empty_string(value.get("cwd")),
        raw_command=normalize_non_empty_string(value.get("rawCommand")),
        agent_id=normalize_non_empty_string(value.get("agentId")),
        session_key=normalize_non_empty_string(value.get("sessionKey")),
        mutable_file_operand=mfo,
    )


@dataclass
class SystemRunApprovalBinding:
    argv: list[str] = field(default_factory=list)
    cwd: str | None = None
    agent_id: str | None = None
    session_key: str | None = None
    env_hash: str | None = None


def _normalize_env_var_key(key: str) -> str | None:
    """Normalize an environment variable key (portable POSIX-safe)."""
    trimmed = key.strip()
    if not trimmed:
        return None
    if not re.match(r'^[A-Za-z_][A-Za-z0-9_]*$', trimmed):
        return None
    return trimmed


def _normalize_system_run_env_entries(env: Any) -> list[tuple[str, str]]:
    if not isinstance(env, dict):
        return []
    entries: list[tuple[str, str]] = []
    for raw_key, raw_value in env.items():
        if not isinstance(raw_value, str):
            continue
        key = _normalize_env_var_key(raw_key)
        if not key:
            continue
        entries.append((key, raw_value))
    entries.sort(key=lambda x: x[0])
    return entries


def _hash_env_entries(entries: list[tuple[str, str]]) -> str | None:
    if not entries:
        return None
    import json
    data = json.dumps(entries)
    return hashlib.sha256(data.encode()).hexdigest()


def build_system_run_approval_env_binding(env: Any) -> tuple[str | None, list[str]]:
    """Build env hash and key list for approval binding. Returns (env_hash, env_keys)."""
    entries = _normalize_system_run_env_entries(env)
    return _hash_env_entries(entries), [k for k, _ in entries]


def build_system_run_approval_binding(
    argv: Any,
    cwd: Any = None,
    agent_id: Any = None,
    session_key: Any = None,
    env: Any = None,
) -> tuple[SystemRunApprovalBinding, list[str]]:
    """Build an approval binding from parameters. Returns (binding, env_keys)."""
    env_hash, env_keys = build_system_run_approval_env_binding(env)
    return SystemRunApprovalBinding(
        argv=normalize_string_array(argv),
        cwd=normalize_non_empty_string(cwd),
        agent_id=normalize_non_empty_string(agent_id),
        session_key=normalize_non_empty_string(session_key),
        env_hash=env_hash,
    ), env_keys


@dataclass
class ApprovalMatchResult:
    ok: bool = True
    code: str = ""
    message: str = ""
    details: dict[str, Any] | None = None


def match_approval_env_hash(
    expected_env_hash: str | None,
    actual_env_hash: str | None,
    actual_env_keys: list[str],
) -> ApprovalMatchResult:
    """Match env hash bindings."""
    if not expected_env_hash and not actual_env_hash:
        return ApprovalMatchResult()
    if not expected_env_hash and actual_env_hash:
        return ApprovalMatchResult(
            ok=False, code="APPROVAL_ENV_BINDING_MISSING",
            message="approval id missing env binding for requested env overrides",
            details={"envKeys": actual_env_keys},
        )
    if expected_env_hash != actual_env_hash:
        return ApprovalMatchResult(
            ok=False, code="APPROVAL_ENV_MISMATCH",
            message="approval id env binding mismatch",
            details={"envKeys": actual_env_keys,
                      "expectedEnvHash": expected_env_hash,
                      "actualEnvHash": actual_env_hash},
        )
    return ApprovalMatchResult()


def match_system_run_approval_binding(
    expected: SystemRunApprovalBinding,
    actual: SystemRunApprovalBinding,
    actual_env_keys: list[str],
) -> ApprovalMatchResult:
    """Match two approval bindings for consistency."""
    if expected.argv != actual.argv:
        return ApprovalMatchResult(ok=False, code="APPROVAL_REQUEST_MISMATCH",
                                   message="approval id does not match request")
    if expected.cwd != actual.cwd:
        return ApprovalMatchResult(ok=False, code="APPROVAL_REQUEST_MISMATCH",
                                   message="approval id does not match request")
    if expected.agent_id != actual.agent_id:
        return ApprovalMatchResult(ok=False, code="APPROVAL_REQUEST_MISMATCH",
                                   message="approval id does not match request")
    if expected.session_key != actual.session_key:
        return ApprovalMatchResult(ok=False, code="APPROVAL_REQUEST_MISMATCH",
                                   message="approval id does not match request")
    return match_approval_env_hash(expected.env_hash, actual.env_hash, actual_env_keys)


# ─── system-run-approval-context.ts ───

@dataclass
class PreparedRunPayload:
    cmd_text: str = ""
    plan: SystemRunApprovalPlan | None = None


def parse_prepared_system_run_payload(payload: Any) -> PreparedRunPayload | None:
    if not isinstance(payload, dict):
        return None
    cmd_text = normalize_non_empty_string(payload.get("cmdText"))
    plan = normalize_system_run_approval_plan(payload.get("plan"))
    if not cmd_text or not plan:
        return None
    return PreparedRunPayload(cmd_text=cmd_text, plan=plan)


@dataclass
class SystemRunApprovalRequestContext:
    plan: SystemRunApprovalPlan | None = None
    command_argv: list[str] | None = None
    command_text: str = ""
    cwd: str | None = None
    agent_id: str | None = None
    session_key: str | None = None


def resolve_system_run_approval_request_context(
    host: Any = None,
    command: Any = None,
    command_argv: Any = None,
    system_run_plan: Any = None,
    cwd: Any = None,
    agent_id: Any = None,
    session_key: Any = None,
) -> SystemRunApprovalRequestContext:
    """Resolve approval request context from tool call parameters."""
    host_str = normalize_non_empty_string(host) or ""
    plan = normalize_system_run_approval_plan(system_run_plan) if host_str == "node" else None
    fallback_argv = normalize_string_array(command_argv)
    fallback_cmd = command if isinstance(command, str) else ""
    return SystemRunApprovalRequestContext(
        plan=plan,
        command_argv=plan.argv if plan else (fallback_argv if fallback_argv else None),
        command_text=plan.raw_command or format_exec_command(plan.argv) if plan else fallback_cmd,
        cwd=plan.cwd if plan else normalize_non_empty_string(cwd),
        agent_id=plan.agent_id if plan else normalize_non_empty_string(agent_id),
        session_key=plan.session_key if plan else normalize_non_empty_string(session_key),
    )


@dataclass
class SystemRunApprovalRuntimeContext:
    ok: bool = True
    plan: SystemRunApprovalPlan | None = None
    argv: list[str] = field(default_factory=list)
    cwd: str | None = None
    agent_id: str | None = None
    session_key: str | None = None
    raw_command: str | None = None
    message: str = ""
    details: dict[str, Any] | None = None


def resolve_system_run_approval_runtime_context(
    plan: Any = None,
    command: Any = None,
    raw_command: Any = None,
    cwd: Any = None,
    agent_id: Any = None,
    session_key: Any = None,
) -> SystemRunApprovalRuntimeContext:
    """Resolve the runtime context for a system run approval."""
    normalized_plan = normalize_system_run_approval_plan(plan)
    if normalized_plan:
        return SystemRunApprovalRuntimeContext(
            ok=True,
            plan=normalized_plan,
            argv=list(normalized_plan.argv),
            cwd=normalized_plan.cwd,
            agent_id=normalized_plan.agent_id,
            session_key=normalized_plan.session_key,
            raw_command=normalized_plan.raw_command,
        )
    resolved = resolve_system_run_command(command, raw_command)
    if not resolved.ok:
        return SystemRunApprovalRuntimeContext(
            ok=False, message=resolved.message, details=resolved.details,
        )
    return SystemRunApprovalRuntimeContext(
        ok=True,
        argv=resolved.argv,
        cwd=normalize_non_empty_string(cwd),
        agent_id=normalize_non_empty_string(agent_id),
        session_key=normalize_non_empty_string(session_key),
        raw_command=normalize_non_empty_string(raw_command),
    )



# ─── system-run-command.ts ───

@dataclass
class SystemRunResult:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    killed: bool = False
    timed_out: bool = False
    duration_ms: int = 0
    command: str = ""


async def run_system_command(
    command: str,
    args: list[str] | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout_ms: int = 30_000,
    stdin_data: str | None = None,
) -> SystemRunResult:
    """Execute a system command with timeout."""
    cmd_args = [command] + (args or [])
    start = time.time()

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd_args,
            cwd=cwd,
            env={**os.environ, **(env or {})},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE if stdin_data else None,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=stdin_data.encode() if stdin_data else None),
                timeout=timeout_ms / 1000.0,
            )
            duration = int((time.time() - start) * 1000)
            return SystemRunResult(
                stdout=stdout_bytes.decode(errors="replace"),
                stderr=stderr_bytes.decode(errors="replace"),
                exit_code=proc.returncode or 0,
                duration_ms=duration,
                command=normalize_run_command(" ".join(cmd_args)),
            )
        except asyncio.TimeoutError:
            proc.kill()
            duration = int((time.time() - start) * 1000)
            return SystemRunResult(
                exit_code=-1, killed=True, timed_out=True,
                duration_ms=duration,
                command=normalize_run_command(" ".join(cmd_args)),
            )
    except FileNotFoundError:
        return SystemRunResult(exit_code=127, stderr=f"command not found: {command}",
                             command=normalize_run_command(command))
    except Exception as e:
        return SystemRunResult(exit_code=-1, stderr=str(e),
                             command=normalize_run_command(command))


# ─── system-message.ts ───

@dataclass
class SystemMessage:
    text: str = ""
    kind: str = "info"  # "info" | "warn" | "error" | "success"
    timestamp: float = 0.0


def create_system_message(text: str, kind: str = "info") -> SystemMessage:
    return SystemMessage(text=text, kind=kind, timestamp=time.time())


def format_system_message(msg: SystemMessage) -> str:
    prefix = {"info": "ℹ", "warn": "⚠", "error": "✗", "success": "✓"}.get(msg.kind, "•")
    return f"{prefix} {msg.text}"


# ─── system-presence.ts ───

@dataclass
class SystemPresenceInfo:
    version: str = ""
    platform: str = ""
    hostname: str = ""
    uptime_ms: int = 0
    pid: int = 0
    started_at: float = 0.0
    channels: list[str] = field(default_factory=list)
    agents: list[str] = field(default_factory=list)


_presence_info: SystemPresenceInfo | None = None


def register_system_presence(info: SystemPresenceInfo) -> None:
    global _presence_info
    _presence_info = info


def get_system_presence() -> SystemPresenceInfo | None:
    return _presence_info


def format_system_presence(info: SystemPresenceInfo) -> str:
    parts = [
        f"OpenClaw v{info.version}",
        f"Platform: {info.platform}",
        f"Host: {info.hostname}",
        f"PID: {info.pid}",
    ]
    if info.channels:
        parts.append(f"Channels: {', '.join(info.channels)}")
    if info.agents:
        parts.append(f"Agents: {', '.join(info.agents)}")
    if info.uptime_ms > 0:
        from ..util.formatting import format_duration_ms
        parts.append(f"Uptime: {format_duration_ms(info.uptime_ms)}")
    return "\n".join(parts)


# ─── runtime-guard.ts ───

_runtime_guards: dict[str, bool] = {}


def set_runtime_guard(name: str, value: bool = True) -> None:
    _runtime_guards[name] = value


def check_runtime_guard(name: str) -> bool:
    return _runtime_guards.get(name, False)


def clear_runtime_guards() -> None:
    _runtime_guards.clear()


def guard_runtime(name: str, message: str = "") -> None:
    """Raise if runtime guard is set."""
    if _runtime_guards.get(name, False):
        raise RuntimeError(message or f"Runtime guard '{name}' is active")


# ─── runtime-status.ts ───

RuntimeStatus = Literal["starting", "running", "stopping", "stopped", "error"]

_runtime_status: str = "stopped"


def set_runtime_status(status: str) -> None:
    global _runtime_status
    _runtime_status = status


def get_runtime_status() -> str:
    return _runtime_status


def is_runtime_running() -> bool:
    return _runtime_status == "running"
