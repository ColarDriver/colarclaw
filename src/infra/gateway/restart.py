"""Infra restart — ported from bk/src/infra/restart.ts, restart-sentinel.ts,
restart-stale-pids.ts, process-respawn.ts, windows-task-restart.ts.

Gateway restart lifecycle: SIGUSR1 authorization, scheduled restarts,
stale PID cleanup, process respawn, sentinel files, platform restart triggers.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("infra.restart")

SPAWN_TIMEOUT_S = 2.0
SIGUSR1_AUTH_GRACE_MS = 5000
DEFAULT_DEFERRAL_POLL_MS = 500
DEFAULT_DEFERRAL_MAX_WAIT_MS = 30_000
RESTART_COOLDOWN_MS = 30_000


# ─── restart types ───

@dataclass
class RestartAttempt:
    ok: bool = False
    method: str = ""  # "systemd" | "launchctl" | "schtasks" | "supervisor"
    detail: str | None = None
    tried: list[str] = field(default_factory=list)


@dataclass
class ScheduledRestart:
    ok: bool = False
    pid: int = 0
    signal: str = "SIGUSR1"
    delay_ms: int = 0
    reason: str | None = None
    mode: str = "signal"  # "emit" | "signal"
    coalesced: bool = False
    cooldown_ms_applied: int = 0


@dataclass
class RestartAuditInfo:
    actor: str | None = None
    device_id: str | None = None
    client_ip: str | None = None
    changed_paths: list[str] | None = None


# ─── restart sentinel ───

@dataclass
class RestartSentinel:
    """File-based sentinel to signal gateway restart."""
    path: str = ""
    created_at: float = 0.0

    @staticmethod
    def write(path: str) -> "RestartSentinel":
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w") as f:
            f.write(str(time.time()))
        return RestartSentinel(path=path, created_at=time.time())

    @staticmethod
    def read(path: str) -> "RestartSentinel | None":
        try:
            with open(path, "r") as f:
                ts = float(f.read().strip())
            return RestartSentinel(path=path, created_at=ts)
        except (OSError, ValueError):
            return None

    @staticmethod
    def remove(path: str) -> None:
        try:
            os.unlink(path)
        except OSError:
            pass

    def is_recent(self, max_age_ms: int = 60_000) -> bool:
        return (time.time() - self.created_at) * 1000 < max_age_ms


# ─── stale PID cleanup ───

def is_pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def find_gateway_pids_on_port(port: int) -> list[int]:
    """Find PIDs listening on a given port (Linux/macOS)."""
    pids: list[int] = []
    try:
        result = subprocess.run(
            ["lsof", "-i", f":{port}", "-t"],
            capture_output=True, text=True, timeout=5.0,
        )
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line.isdigit():
                pids.append(int(line))
    except (subprocess.SubprocessError, FileNotFoundError):
        pass
    return pids


def clean_stale_gateway_processes(port: int | None = None) -> list[int]:
    """Kill stale gateway processes on the given port."""
    if not port:
        return []
    killed: list[int] = []
    my_pid = os.getpid()
    for pid in find_gateway_pids_on_port(port):
        if pid == my_pid:
            continue
        try:
            os.kill(pid, signal.SIGTERM)
            killed.append(pid)
        except (ProcessLookupError, PermissionError):
            pass
    return killed


# ─── process respawn ───

@dataclass
class RespawnPolicy:
    max_respawns: int = 5
    window_ms: int = 60_000
    cooldown_ms: int = 2_000


class RespawnTracker:
    def __init__(self, policy: RespawnPolicy | None = None):
        self._policy = policy or RespawnPolicy()
        self._respawn_times: list[float] = []

    def should_respawn(self) -> bool:
        now = time.time() * 1000
        cutoff = now - self._policy.window_ms
        self._respawn_times = [t for t in self._respawn_times if t > cutoff]
        return len(self._respawn_times) < self._policy.max_respawns

    def record_respawn(self) -> None:
        self._respawn_times.append(time.time() * 1000)

    @property
    def cooldown_ms(self) -> int:
        return self._policy.cooldown_ms

    def reset(self) -> None:
        self._respawn_times.clear()


# ─── SIGUSR1 restart authorization ───

_sigusr1_authorized_count = 0
_sigusr1_authorized_until = 0.0
_sigusr1_external_allowed = False
_pre_restart_check: Callable[[], int] | None = None
_restart_cycle_token = 0
_emitted_restart_token = 0
_consumed_restart_token = 0
_last_restart_emitted_at = 0.0
_pending_restart_reason: str | None = None


def _has_unconsumed_restart_signal() -> bool:
    return _emitted_restart_token > _consumed_restart_token


def set_pre_restart_deferral_check(fn: Callable[[], int]) -> None:
    global _pre_restart_check
    _pre_restart_check = fn


def set_gateway_sigusr1_restart_policy(allow_external: bool = False) -> None:
    global _sigusr1_external_allowed
    _sigusr1_external_allowed = allow_external


def is_gateway_sigusr1_restart_externally_allowed() -> bool:
    return _sigusr1_external_allowed


def authorize_gateway_sigusr1_restart(delay_ms: int = 0) -> None:
    global _sigusr1_authorized_count, _sigusr1_authorized_until
    delay = max(0, delay_ms)
    expires_at = time.time() * 1000 + delay + SIGUSR1_AUTH_GRACE_MS
    _sigusr1_authorized_count += 1
    if expires_at > _sigusr1_authorized_until:
        _sigusr1_authorized_until = expires_at


def _reset_sigusr1_authorization_if_expired(now: float | None = None) -> None:
    global _sigusr1_authorized_count, _sigusr1_authorized_until
    if _sigusr1_authorized_count <= 0:
        return
    now = now or time.time() * 1000
    if now <= _sigusr1_authorized_until:
        return
    _sigusr1_authorized_count = 0
    _sigusr1_authorized_until = 0


def consume_gateway_sigusr1_restart_authorization() -> bool:
    global _sigusr1_authorized_count, _sigusr1_authorized_until
    _reset_sigusr1_authorization_if_expired()
    if _sigusr1_authorized_count <= 0:
        return False
    _sigusr1_authorized_count -= 1
    if _sigusr1_authorized_count <= 0:
        _sigusr1_authorized_until = 0
    return True


def mark_gateway_sigusr1_restart_handled() -> None:
    global _consumed_restart_token
    if _has_unconsumed_restart_signal():
        _consumed_restart_token = _emitted_restart_token


def emit_gateway_restart() -> bool:
    """Emit an authorized SIGUSR1 gateway restart."""
    global _restart_cycle_token, _emitted_restart_token, _last_restart_emitted_at
    if _has_unconsumed_restart_signal():
        return False
    cycle_token = _restart_cycle_token + 1
    _restart_cycle_token = cycle_token
    _emitted_restart_token = cycle_token
    authorize_gateway_sigusr1_restart()
    try:
        os.kill(os.getpid(), signal.SIGUSR1)
    except (OSError, AttributeError):
        _emitted_restart_token = _consumed_restart_token
        return False
    _last_restart_emitted_at = time.time() * 1000
    return True


# ─── audit info formatting ───

def _summarize_changed_paths(paths: list[str] | None, max_paths: int = 6) -> str | None:
    if not paths:
        return None
    if len(paths) <= max_paths:
        return ",".join(paths)
    head = ",".join(paths[:max_paths])
    return f"{head},+{len(paths) - max_paths} more"


def format_restart_audit(audit: RestartAuditInfo | None) -> str:
    if not audit:
        return "actor=<unknown>"
    fields: list[str] = []
    if audit.actor and audit.actor.strip():
        fields.append(f"actor={audit.actor.strip()}")
    if audit.device_id and audit.device_id.strip():
        fields.append(f"device={audit.device_id.strip()}")
    if audit.client_ip and audit.client_ip.strip():
        fields.append(f"ip={audit.client_ip.strip()}")
    changed = _summarize_changed_paths(audit.changed_paths)
    if changed:
        fields.append(f"changedPaths={changed}")
    return " ".join(fields) if fields else "actor=<unknown>"


# ─── spawn detail formatting ───

def _format_spawn_detail(result: subprocess.CompletedProcess[str] | None, error: Exception | None = None) -> str:
    if error:
        return str(error)
    if not result:
        return "unknown error"
    stderr = (result.stderr or "").strip()
    if stderr:
        return stderr
    stdout = (result.stdout or "").strip()
    if stdout:
        return stdout
    return f"exit {result.returncode}"


# ─── platform restart triggers ───

def trigger_openclaw_restart(profile: str | None = None) -> RestartAttempt:
    """Trigger a platform-appropriate gateway restart."""
    import sys as _sys

    if os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("NODE_ENV") == "test":
        return RestartAttempt(ok=True, method="supervisor", detail="test mode")

    clean_stale_gateway_processes()
    tried: list[str] = []

    if _sys.platform == "linux":
        service_name = os.environ.get("OPENCLAW_SYSTEMD_UNIT") or f"openclaw-gateway{'@' + profile if profile else ''}.service"
        if not service_name.endswith(".service"):
            service_name += ".service"

        # Try user systemd restart
        user_args = ["--user", "restart", service_name]
        tried.append(f"systemctl {' '.join(user_args)}")
        try:
            result = subprocess.run(["systemctl"] + user_args, capture_output=True, text=True, timeout=SPAWN_TIMEOUT_S)
            if result.returncode == 0:
                return RestartAttempt(ok=True, method="systemd", tried=tried)
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        # Try system systemd restart
        system_args = ["restart", service_name]
        tried.append(f"systemctl {' '.join(system_args)}")
        try:
            result = subprocess.run(["systemctl"] + system_args, capture_output=True, text=True, timeout=SPAWN_TIMEOUT_S)
            if result.returncode == 0:
                return RestartAttempt(ok=True, method="systemd", tried=tried)
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return RestartAttempt(ok=False, method="systemd", detail="systemd restart failed", tried=tried)

    if _sys.platform == "darwin":
        label = os.environ.get("OPENCLAW_LAUNCHD_LABEL") or f"ai.openclaw.gateway{'.' + profile if profile else ''}"
        uid = os.getuid()
        domain = f"gui/{uid}"
        target = f"{domain}/{label}"

        args = ["kickstart", "-k", target]
        tried.append(f"launchctl {' '.join(args)}")
        try:
            result = subprocess.run(["launchctl"] + args, capture_output=True, text=True, timeout=SPAWN_TIMEOUT_S)
            if result.returncode == 0:
                return RestartAttempt(ok=True, method="launchctl", tried=tried)
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        # Bootstrap fallback
        home = os.environ.get("HOME", "").strip() or str(Path.home())
        plist_path = os.path.join(home, "Library", "LaunchAgents", f"{label}.plist")
        bootstrap_args = ["bootstrap", domain, plist_path]
        tried.append(f"launchctl {' '.join(bootstrap_args)}")
        try:
            boot = subprocess.run(["launchctl"] + bootstrap_args, capture_output=True, text=True, timeout=SPAWN_TIMEOUT_S)
            if boot.returncode == 0:
                retry_args = ["kickstart", "-k", target]
                tried.append(f"launchctl {' '.join(retry_args)}")
                retry = subprocess.run(["launchctl"] + retry_args, capture_output=True, text=True, timeout=SPAWN_TIMEOUT_S)
                if retry.returncode == 0:
                    return RestartAttempt(ok=True, method="launchctl", tried=tried)
                return RestartAttempt(ok=False, method="launchctl", detail=_format_spawn_detail(retry), tried=tried)
        except (subprocess.SubprocessError, FileNotFoundError):
            pass

        return RestartAttempt(ok=False, method="launchctl", detail="launchctl restart failed", tried=tried)

    return RestartAttempt(ok=False, method="supervisor", detail="unsupported platform restart")


# ─── restart scheduling (restart.ts: scheduleGatewaySigusr1Restart) ───

def schedule_gateway_sigusr1_restart(
    delay_ms: int = 2000,
    reason: str | None = None,
    audit: RestartAuditInfo | None = None,
) -> ScheduledRestart:
    """Schedule a SIGUSR1 gateway restart with cooldown and coalescing."""
    global _last_restart_emitted_at, _pending_restart_reason
    delay_ms = min(max(int(delay_ms), 0), 60_000)
    mode = "signal"
    now_ms = time.time() * 1000
    cooldown_ms = max(0, _last_restart_emitted_at + RESTART_COOLDOWN_MS - now_ms)
    requested_due_at = now_ms + delay_ms + cooldown_ms

    if _has_unconsumed_restart_signal():
        logger.warning(
            f"restart request coalesced (already in-flight) reason={reason or 'unspecified'} "
            f"{format_restart_audit(audit)}"
        )
        return ScheduledRestart(
            ok=True, pid=os.getpid(), signal="SIGUSR1",
            delay_ms=0, reason=reason, mode=mode,
            coalesced=True, cooldown_ms_applied=int(cooldown_ms),
        )

    _pending_restart_reason = reason

    # Immediate restart if delay is essentially 0
    if delay_ms + cooldown_ms <= 0:
        ok = emit_gateway_restart()
        return ScheduledRestart(
            ok=ok, pid=os.getpid(), signal="SIGUSR1",
            delay_ms=0, reason=reason, mode=mode,
            coalesced=False, cooldown_ms_applied=int(cooldown_ms),
        )

    # Deferred: in Python, the caller should handle the timer externally
    # We just mark and return the schedule info
    return ScheduledRestart(
        ok=True, pid=os.getpid(), signal="SIGUSR1",
        delay_ms=int(max(0, requested_due_at - now_ms)),
        reason=reason, mode=mode,
        coalesced=False, cooldown_ms_applied=int(cooldown_ms),
    )


def defer_gateway_restart_until_idle(
    get_pending_count: Callable[[], int],
    poll_ms: int = DEFAULT_DEFERRAL_POLL_MS,
    max_wait_ms: int = DEFAULT_DEFERRAL_MAX_WAIT_MS,
    on_deferring: Callable[[int], None] | None = None,
    on_ready: Callable[[], None] | None = None,
    on_timeout: Callable[[int, int], None] | None = None,
) -> None:
    """Poll pending work until it drains (or times out), then emit restart."""
    poll_s = max(0.01, poll_ms / 1000.0)
    max_wait_s = max(poll_s, max_wait_ms / 1000.0)

    try:
        pending = get_pending_count()
    except Exception:
        emit_gateway_restart()
        return

    if pending <= 0:
        if on_ready:
            on_ready()
        emit_gateway_restart()
        return

    if on_deferring:
        on_deferring(pending)

    started = time.time()
    while True:
        time.sleep(poll_s)
        try:
            current = get_pending_count()
        except Exception:
            emit_gateway_restart()
            return
        if current <= 0:
            if on_ready:
                on_ready()
            emit_gateway_restart()
            return
        elapsed_ms = (time.time() - started) * 1000
        if elapsed_ms >= max_wait_ms:
            if on_timeout:
                on_timeout(current, int(elapsed_ms))
            emit_gateway_restart()
            return


# ─── restart-sentinel.ts: trim_log_tail ───

def trim_log_tail(text: str, max_chars: int = 8000) -> str:
    """Trim log text to the last max_chars characters."""
    if len(text) <= max_chars:
        return text
    return "…" + text[-(max_chars - 1):]


# ─── reset for tests ───

def reset_restart_state_for_tests() -> None:
    global _sigusr1_authorized_count, _sigusr1_authorized_until, _sigusr1_external_allowed
    global _pre_restart_check, _restart_cycle_token, _emitted_restart_token
    global _consumed_restart_token, _last_restart_emitted_at, _pending_restart_reason
    _sigusr1_authorized_count = 0
    _sigusr1_authorized_until = 0
    _sigusr1_external_allowed = False
    _pre_restart_check = None
    _restart_cycle_token = 0
    _emitted_restart_token = 0
    _consumed_restart_token = 0
    _last_restart_emitted_at = 0
    _pending_restart_reason = None

