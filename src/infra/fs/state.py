"""Infra state migrations — ported from bk/src/infra/state-migrations.ts,
state-migrations.fs.ts, openclaw-root.ts, tmp-openclaw-dir.ts,
os-summary.ts, supervisor-markers.ts, machine-name.ts, transport-ready.ts,
warning-filter.ts, voicewake.ts, is-main.ts, wsl.ts.

State directory migrations, root resolution, temp dirs, OS summaries,
supervisor markers, transport readiness, warning filters, misc utilities.
"""
from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger("infra.state")


# ─── openclaw-root.ts ───

def resolve_openclaw_root(env: dict[str, str] | None = None) -> str:
    """Resolve the OpenClaw root directory."""
    e = env or os.environ
    explicit = e.get("OPENCLAW_ROOT", "").strip()
    if explicit and os.path.isdir(explicit):
        return os.path.abspath(explicit)
    # Walk up from current file to find package root
    current = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        if os.path.isfile(os.path.join(current, "pyproject.toml")) or os.path.isfile(os.path.join(current, "package.json")):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return os.getcwd()


def resolve_openclaw_state_dir_v2(env: dict[str, str] | None = None) -> str:
    e = env or os.environ
    explicit = e.get("OPENCLAW_STATE_DIR", "").strip()
    if explicit:
        return os.path.abspath(explicit)
    return os.path.join(str(Path.home()), ".openclaw")


# ─── tmp-openclaw-dir.ts ───

def resolve_tmp_openclaw_dir(env: dict[str, str] | None = None) -> str:
    """Resolve the temporary OpenClaw directory."""
    e = env or os.environ
    explicit = e.get("OPENCLAW_TMP_DIR", "").strip()
    if explicit:
        return os.path.abspath(explicit)
    import tempfile
    return os.path.join(tempfile.gettempdir(), "openclaw")


def ensure_tmp_openclaw_dir(env: dict[str, str] | None = None) -> str:
    path = resolve_tmp_openclaw_dir(env)
    os.makedirs(path, exist_ok=True)
    return path


def clean_tmp_openclaw_dir(max_age_hours: float = 24.0) -> int:
    """Clean old temp files. Returns count of removed items."""
    tmp_dir = resolve_tmp_openclaw_dir()
    if not os.path.isdir(tmp_dir):
        return 0
    cutoff = time.time() - max_age_hours * 3600
    removed = 0
    try:
        for entry in os.scandir(tmp_dir):
            try:
                if entry.stat().st_mtime < cutoff:
                    if entry.is_dir(follow_symlinks=False):
                        shutil.rmtree(entry.path, ignore_errors=True)
                    else:
                        os.unlink(entry.path)
                    removed += 1
            except OSError:
                pass
    except OSError:
        pass
    return removed


# ─── os-summary.ts ───

@dataclass
class OsSummary:
    platform: str = ""
    arch: str = ""
    release: str = ""
    hostname: str = ""
    home_dir: str = ""
    username: str = ""
    python_version: str = ""
    cpu_count: int | None = None


def get_os_summary() -> OsSummary:
    return OsSummary(
        platform=sys.platform,
        arch=platform.machine(),
        release=platform.release(),
        hostname=platform.node(),
        home_dir=str(Path.home()),
        username=os.getenv("USER", os.getenv("USERNAME", "unknown")),
        python_version=platform.python_version(),
        cpu_count=os.cpu_count(),
    )


def format_os_summary(summary: OsSummary | None = None) -> str:
    s = summary or get_os_summary()
    return f"{s.platform} {s.arch} (Python {s.python_version}, {s.cpu_count or '?'} CPUs)"


# ─── machine-name.ts ───

def get_machine_name() -> str:
    """Get a human-readable machine name."""
    hostname = platform.node()
    if hostname:
        # Strip common suffixes
        for suffix in (".local", ".lan", ".home"):
            if hostname.endswith(suffix):
                hostname = hostname[:-len(suffix)]
        return hostname
    return os.getenv("HOSTNAME", "unknown")


# ─── supervisor-markers.ts ───

@dataclass
class SupervisorMarker:
    kind: str = ""  # "started" | "stopped" | "restarted" | "error"
    timestamp: float = 0.0
    pid: int = 0
    detail: str | None = None


def write_supervisor_marker(path: str, kind: str, detail: str | None = None) -> None:
    import json
    marker = SupervisorMarker(kind=kind, timestamp=time.time(), pid=os.getpid(), detail=detail)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump({"kind": marker.kind, "timestamp": marker.timestamp,
                    "pid": marker.pid, "detail": marker.detail}, f)


def read_supervisor_marker(path: str) -> SupervisorMarker | None:
    import json
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return SupervisorMarker(**data)
    except (OSError, json.JSONDecodeError, TypeError):
        return None


# ─── transport-ready.ts ───

@dataclass
class TransportReadyState:
    ready: bool = False
    channels: list[str] = field(default_factory=list)
    pending_channels: list[str] = field(default_factory=list)
    error: str | None = None


_transport_ready_handlers: list[Callable[[], None]] = []


def on_transport_ready(handler: Callable[[], None]) -> Callable[[], None]:
    _transport_ready_handlers.append(handler)
    def dispose():
        try:
            _transport_ready_handlers.remove(handler)
        except ValueError:
            pass
    return dispose


def emit_transport_ready() -> None:
    for handler in _transport_ready_handlers:
        try:
            handler()
        except Exception:
            pass


# ─── warning-filter.ts ───

_warning_filters: list[re.Pattern[str]] = []
_suppressed_warnings: list[str] = []


def add_warning_filter(pattern: str) -> None:
    try:
        _warning_filters.append(re.compile(pattern, re.I))
    except re.error:
        pass


def should_suppress_warning(message: str) -> bool:
    for pattern in _warning_filters:
        if pattern.search(message):
            _suppressed_warnings.append(message)
            return True
    return False


def get_suppressed_warning_count() -> int:
    return len(_suppressed_warnings)


def clear_warning_filters() -> None:
    _warning_filters.clear()
    _suppressed_warnings.clear()


# ─── voicewake.ts ───

@dataclass
class VoiceWakeConfig:
    enabled: bool = False
    wake_words: list[str] = field(default_factory=lambda: ["hey openclaw"])
    command_template: str = 'openclaw agent --message "${text}" --thinking low'
    timeout_s: float = 30.0


def resolve_voice_wake_config(env: dict[str, str] | None = None) -> VoiceWakeConfig:
    e = env or os.environ
    enabled = (e.get("OPENCLAW_VOICE_WAKE", "").strip().lower() in ("true", "1", "yes"))
    return VoiceWakeConfig(enabled=enabled)


# ─── is-main.ts ───

def is_main_module(filepath: str) -> bool:
    """Check if a module is the main entry point."""
    return os.path.abspath(filepath) == os.path.abspath(sys.argv[0]) if sys.argv else False


# ─── wsl.ts ───

_is_wsl: bool | None = None


def is_wsl() -> bool:
    """Check if running under Windows Subsystem for Linux."""
    global _is_wsl
    if _is_wsl is not None:
        return _is_wsl
    if sys.platform != "linux":
        _is_wsl = False
        return False
    try:
        with open("/proc/version", "r") as f:
            version = f.read().lower()
        _is_wsl = "microsoft" in version or "wsl" in version
    except OSError:
        _is_wsl = False
    return _is_wsl


def get_wsl_version() -> int | None:
    """Get WSL version (1 or 2)."""
    if not is_wsl():
        return None
    try:
        with open("/proc/version", "r") as f:
            version = f.read().lower()
        if "wsl2" in version:
            return 2
        return 1
    except OSError:
        return None


# ─── state-migrations.ts ───

@dataclass
class StateMigration:
    version: int = 0
    description: str = ""
    migrate_fn: Callable[[], bool] | None = None


_migrations: list[StateMigration] = []


def register_state_migration(version: int, description: str, fn: Callable[[], bool]) -> None:
    _migrations.append(StateMigration(version=version, description=description, migrate_fn=fn))
    _migrations.sort(key=lambda m: m.version)


def get_current_state_version(state_dir: str) -> int:
    version_file = os.path.join(state_dir, ".state-version")
    try:
        with open(version_file, "r") as f:
            return int(f.read().strip())
    except (OSError, ValueError):
        return 0


def set_state_version(state_dir: str, version: int) -> None:
    version_file = os.path.join(state_dir, ".state-version")
    os.makedirs(state_dir, exist_ok=True)
    with open(version_file, "w") as f:
        f.write(str(version))


def run_state_migrations(state_dir: str) -> list[str]:
    """Run pending state migrations. Returns list of applied migration descriptions."""
    current = get_current_state_version(state_dir)
    applied: list[str] = []
    for migration in _migrations:
        if migration.version <= current:
            continue
        logger.info(f"Running state migration v{migration.version}: {migration.description}")
        if migration.migrate_fn:
            try:
                ok = migration.migrate_fn()
                if ok:
                    set_state_version(state_dir, migration.version)
                    applied.append(migration.description)
                else:
                    logger.error(f"Migration v{migration.version} failed")
                    break
            except Exception as e:
                logger.error(f"Migration v{migration.version} error: {e}")
                break
        else:
            set_state_version(state_dir, migration.version)
            applied.append(migration.description)
    return applied


# ─── state-migrations.ts: legacy state detection & auto-migration ───

@dataclass
class FileCopyPlan:
    label: str = ""
    source_path: str = ""
    target_path: str = ""


@dataclass
class SessionMigrationInfo:
    legacy_dir: str = ""
    legacy_store_path: str = ""
    target_dir: str = ""
    target_store_path: str = ""
    has_legacy: bool = False
    legacy_keys: list[str] = field(default_factory=list)


@dataclass
class AgentDirMigration:
    legacy_dir: str = ""
    target_dir: str = ""
    has_legacy: bool = False


@dataclass
class LegacyStateDetection:
    target_agent_id: str = "main"
    target_main_key: str = "main"
    state_dir: str = ""
    oauth_dir: str = ""
    sessions: SessionMigrationInfo = field(default_factory=SessionMigrationInfo)
    agent_dir: AgentDirMigration = field(default_factory=AgentDirMigration)
    preview: list[str] = field(default_factory=list)


@dataclass
class StateDirMigrationResult:
    migrated: bool = False
    skipped: bool = False
    changes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


_auto_migrate_checked = False
_auto_migrate_state_dir_checked = False


def reset_auto_migrate_for_test() -> None:
    global _auto_migrate_checked, _auto_migrate_state_dir_checked
    _auto_migrate_checked = False
    _auto_migrate_state_dir_checked = False


def _resolve_symlink_target(link_path: str) -> str | None:
    try:
        target = os.readlink(link_path)
        return os.path.normpath(os.path.join(os.path.dirname(link_path), target))
    except OSError:
        return None


def _is_within_dir(root: str, path_to_check: str) -> bool:
    root = os.path.realpath(root)
    target = os.path.realpath(path_to_check)
    if not root.endswith(os.sep):
        root += os.sep
    return target.startswith(root) or target == root.rstrip(os.sep)


def _is_surface_group_key(key: str) -> bool:
    return ":group:" in key or ":channel:" in key


def _is_legacy_group_key(key: str) -> bool:
    trimmed = key.strip()
    if not trimmed:
        return False
    if trimmed.startswith("group:"):
        return True
    lower = trimmed.lower()
    if "@g.us" not in lower:
        return False
    if ":" not in trimmed:
        return True
    if lower.startswith("whatsapp:") and ":group:" not in trimmed:
        return True
    return False


def _canonicalize_session_key(key: str, agent_id: str, main_key: str) -> str:
    """Canonicalize a legacy session key into the new agent-scoped format."""
    raw = key.strip()
    if not raw:
        return raw
    lower = raw.lower()
    if lower in ("global", "unknown"):
        return lower

    # Already agent-scoped
    if lower.startswith("agent:"):
        return lower

    # "main" / main_key aliases
    if lower == "main" or lower == main_key.lower():
        return f"agent:{agent_id}:main"

    if lower.startswith("subagent:"):
        rest = raw[len("subagent:"):]
        return f"agent:{agent_id}:subagent:{rest}".lower()

    if raw.startswith("group:"):
        gid = raw[len("group:"):].strip()
        if not gid:
            return raw
        channel = "whatsapp" if "@g.us" in gid.lower() else "unknown"
        return f"agent:{agent_id}:{channel}:group:{gid}".lower()

    if ":" not in raw and "@g.us" in lower:
        return f"agent:{agent_id}:whatsapp:group:{raw}".lower()

    if lower.startswith("whatsapp:") and "@g.us" in lower:
        remainder = raw[len("whatsapp:"):].strip()
        cleaned = re.sub(r"^group:", "", remainder, flags=re.IGNORECASE).strip()
        if cleaned and not _is_surface_group_key(raw):
            return f"agent:{agent_id}:whatsapp:group:{cleaned}".lower()

    if _is_surface_group_key(raw):
        return f"agent:{agent_id}:{raw}".lower()

    return f"agent:{agent_id}:{raw}".lower()


def _list_legacy_session_keys(store: dict[str, Any], agent_id: str, main_key: str) -> list[str]:
    legacy = []
    for key in store:
        canonical = _canonicalize_session_key(key, agent_id, main_key)
        if canonical != key:
            legacy.append(key)
    return legacy


def _canonicalize_session_store(store: dict[str, Any], agent_id: str, main_key: str) -> tuple[dict[str, Any], list[str]]:
    """Canonicalize session keys in a store. Returns (canonical_store, legacy_keys)."""
    canonical: dict[str, Any] = {}
    legacy_keys: list[str] = []
    for key, entry in store.items():
        if not isinstance(entry, dict):
            continue
        ckey = _canonicalize_session_key(key, agent_id, main_key)
        if ckey != key:
            legacy_keys.append(key)
        existing = canonical.get(ckey)
        if not existing:
            canonical[ckey] = entry
            continue
        # Pick the most recently updated entry
        incoming_ts = entry.get("updatedAt", 0) or 0
        existing_ts = existing.get("updatedAt", 0) or 0
        if incoming_ts > existing_ts:
            canonical[ckey] = entry
    return canonical, legacy_keys


def _safe_read_json(path_str: str) -> dict[str, Any] | None:
    try:
        with open(path_str, "r") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def detect_legacy_state_migrations(
    state_dir: str,
    agent_id: str = "main",
    main_key: str = "main",
) -> LegacyStateDetection:
    """Detect legacy state that needs migration."""
    import json
    oauth_dir = os.path.join(state_dir, "credentials")

    # Sessions
    sessions_legacy_dir = os.path.join(state_dir, "sessions")
    sessions_legacy_store = os.path.join(sessions_legacy_dir, "sessions.json")
    sessions_target_dir = os.path.join(state_dir, "agents", agent_id, "sessions")
    sessions_target_store = os.path.join(sessions_target_dir, "sessions.json")

    has_legacy_sessions = os.path.isfile(sessions_legacy_store) or any(
        f.endswith(".jsonl") for f in os.listdir(sessions_legacy_dir)
        if os.path.isfile(os.path.join(sessions_legacy_dir, f))
    ) if os.path.isdir(sessions_legacy_dir) else False

    target_store = _safe_read_json(sessions_target_store) or {}
    legacy_keys = _list_legacy_session_keys(target_store, agent_id, main_key)

    # Agent dir
    legacy_agent_dir = os.path.join(state_dir, "agent")
    target_agent_dir = os.path.join(state_dir, "agents", agent_id, "agent")
    has_legacy_agent_dir = os.path.isdir(legacy_agent_dir)

    preview: list[str] = []
    if has_legacy_sessions:
        preview.append(f"- Sessions: {sessions_legacy_dir} → {sessions_target_dir}")
    if legacy_keys:
        preview.append(f"- Sessions: canonicalize {len(legacy_keys)} legacy key(s) in {sessions_target_store}")
    if has_legacy_agent_dir:
        preview.append(f"- Agent dir: {legacy_agent_dir} → {target_agent_dir}")

    return LegacyStateDetection(
        target_agent_id=agent_id,
        target_main_key=main_key,
        state_dir=state_dir,
        oauth_dir=oauth_dir,
        sessions=SessionMigrationInfo(
            legacy_dir=sessions_legacy_dir,
            legacy_store_path=sessions_legacy_store,
            target_dir=sessions_target_dir,
            target_store_path=sessions_target_store,
            has_legacy=has_legacy_sessions or len(legacy_keys) > 0,
            legacy_keys=legacy_keys,
        ),
        agent_dir=AgentDirMigration(
            legacy_dir=legacy_agent_dir,
            target_dir=target_agent_dir,
            has_legacy=has_legacy_agent_dir,
        ),
        preview=preview,
    )


def auto_migrate_legacy_state_dir(
    env: dict[str, str] | None = None,
    legacy_dirs: list[str] | None = None,
    target_dir: str | None = None,
) -> StateDirMigrationResult:
    """Auto-migrate legacy state directory to new location."""
    global _auto_migrate_state_dir_checked
    if _auto_migrate_state_dir_checked:
        return StateDirMigrationResult(skipped=True)
    _auto_migrate_state_dir_checked = True

    env = env or os.environ
    if env.get("OPENCLAW_STATE_DIR", "").strip():
        return StateDirMigrationResult(skipped=True)

    home = str(Path.home())
    target = target_dir or os.path.join(home, ".openclaw")
    legacy_candidates = legacy_dirs or [
        os.path.join(home, ".clawd"),  # Legacy name
    ]

    warnings: list[str] = []
    changes: list[str] = []

    legacy_dir = None
    for candidate in legacy_candidates:
        if os.path.exists(candidate):
            legacy_dir = candidate
            break

    if not legacy_dir:
        return StateDirMigrationResult(changes=changes, warnings=warnings)

    try:
        lst = os.lstat(legacy_dir)
    except OSError:
        return StateDirMigrationResult(changes=changes, warnings=warnings)

    if not (os.path.isdir(legacy_dir) or os.path.islink(legacy_dir)):
        warnings.append(f"Legacy state path is not a directory: {legacy_dir}")
        return StateDirMigrationResult(changes=changes, warnings=warnings)

    # If symlink, check if it already points to target
    if os.path.islink(legacy_dir):
        link_target = _resolve_symlink_target(legacy_dir)
        if link_target and os.path.abspath(link_target) == os.path.abspath(target):
            return StateDirMigrationResult(changes=changes, warnings=warnings)
        warnings.append(f"Legacy state dir is a symlink: {legacy_dir}; skipping")
        return StateDirMigrationResult(changes=changes, warnings=warnings)

    # Target already exists
    if os.path.isdir(target):
        warnings.append(f"Target already exists: {target}; skipping auto-migration")
        return StateDirMigrationResult(changes=changes, warnings=warnings)

    # Move and symlink
    try:
        os.rename(legacy_dir, target)
    except OSError as e:
        warnings.append(f"Failed to move {legacy_dir} → {target}: {e}")
        return StateDirMigrationResult(changes=changes, warnings=warnings)

    try:
        os.symlink(target, legacy_dir)
        changes.append(f"State dir: {legacy_dir} → {target} (legacy path now symlinked)")
    except OSError as e:
        # Try to roll back
        try:
            os.rename(target, legacy_dir)
            warnings.append(f"Rolled back migration, failed to create symlink: {e}")
        except OSError as rollback_err:
            warnings.append(f"State dir moved but symlink failed: {e}; rollback failed: {rollback_err}")
            warnings.append(f"Set OPENCLAW_STATE_DIR={target} to avoid split state")
            changes.append(f"State dir: {legacy_dir} → {target}")

    return StateDirMigrationResult(
        migrated=len(changes) > 0,
        changes=changes,
        warnings=warnings,
    )


def migrate_legacy_sessions(detected: LegacyStateDetection) -> StateDirMigrationResult:
    """Migrate legacy sessions from old layout to agent-scoped layout."""
    import json
    changes: list[str] = []
    warnings: list[str] = []

    if not detected.sessions.has_legacy:
        return StateDirMigrationResult(changes=changes, warnings=warnings)

    os.makedirs(detected.sessions.target_dir, exist_ok=True)

    # Read and merge stores
    legacy_store = _safe_read_json(detected.sessions.legacy_store_path) or {}
    target_store = _safe_read_json(detected.sessions.target_store_path) or {}

    target_canonical, target_lk = _canonicalize_session_store(
        target_store, detected.target_agent_id, detected.target_main_key)
    legacy_canonical, legacy_lk = _canonicalize_session_store(
        legacy_store, detected.target_agent_id, detected.target_main_key)

    # Merge legacy into target (target wins ties)
    merged = dict(target_canonical)
    for key, entry in legacy_canonical.items():
        if key not in merged:
            merged[key] = entry
        else:
            incoming_ts = entry.get("updatedAt", 0) or 0
            existing_ts = merged[key].get("updatedAt", 0) or 0
            if incoming_ts > existing_ts:
                merged[key] = entry

    # Save merged store
    if merged:
        try:
            with open(detected.sessions.target_store_path, "w") as f:
                json.dump(merged, f, indent=2)
                f.write("\n")
            changes.append(f"Merged sessions store → {detected.sessions.target_store_path}")
        except OSError as e:
            warnings.append(f"Failed to save merged sessions: {e}")

    # Copy transcript files
    if os.path.isdir(detected.sessions.legacy_dir):
        for name in os.listdir(detected.sessions.legacy_dir):
            if not name.endswith(".jsonl"):
                continue
            src = os.path.join(detected.sessions.legacy_dir, name)
            dst = os.path.join(detected.sessions.target_dir, name)
            if os.path.exists(dst):
                continue
            try:
                shutil.copy2(src, dst)
                changes.append(f"Copied transcript {name}")
            except OSError as e:
                warnings.append(f"Failed to copy {name}: {e}")

    if target_lk:
        changes.append(f"Canonicalized {len(target_lk)} legacy session key(s)")

    return StateDirMigrationResult(
        migrated=len(changes) > 0,
        changes=changes,
        warnings=warnings,
    )


def migrate_legacy_agent_dir(detected: LegacyStateDetection) -> StateDirMigrationResult:
    """Migrate legacy agent/ directory to agents/<id>/agent/."""
    changes: list[str] = []
    warnings: list[str] = []

    if not detected.agent_dir.has_legacy:
        return StateDirMigrationResult(changes=changes, warnings=warnings)

    if os.path.isdir(detected.agent_dir.target_dir):
        warnings.append(f"Target agent dir already exists: {detected.agent_dir.target_dir}")
        return StateDirMigrationResult(changes=changes, warnings=warnings)

    os.makedirs(os.path.dirname(detected.agent_dir.target_dir), exist_ok=True)

    try:
        shutil.copytree(detected.agent_dir.legacy_dir, detected.agent_dir.target_dir)
        changes.append(f"Copied agent dir: {detected.agent_dir.legacy_dir} → {detected.agent_dir.target_dir}")
    except OSError as e:
        warnings.append(f"Failed to copy agent dir: {e}")

    return StateDirMigrationResult(
        migrated=len(changes) > 0,
        changes=changes,
        warnings=warnings,
    )
