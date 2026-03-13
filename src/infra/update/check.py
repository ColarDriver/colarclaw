"""Infra update — ported from bk/src/infra/update-check.ts, update-channels.ts,
update-global.ts, update-runner.ts, update-startup.ts.

Version comparison, update checking, npm registry queries, update channels,
git update status, dependency status checking, update runner.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("infra.update")


# ─── update-channels.ts ───

UpdateChannel = Literal["stable", "beta", "dev"]

CHANNEL_NPM_TAGS: dict[str, str] = {
    "stable": "latest",
    "beta": "beta",
    "dev": "latest",  # dev uses git head
}


def channel_to_npm_tag(channel: UpdateChannel) -> str:
    return CHANNEL_NPM_TAGS.get(channel, "latest")


def resolve_update_channel(raw: str | None = None) -> UpdateChannel:
    if not raw:
        return "stable"
    cleaned = raw.strip().lower()
    if cleaned in ("stable", "beta", "dev"):
        return cleaned  # type: ignore
    return "stable"


# ─── update-check.ts: types ───

PackageManager = Literal["pnpm", "bun", "npm", "unknown"]


@dataclass
class GitUpdateStatus:
    root: str = ""
    sha: str | None = None
    tag: str | None = None
    branch: str | None = None
    upstream: str | None = None
    dirty: bool | None = None
    ahead: int | None = None
    behind: int | None = None
    fetch_ok: bool | None = None
    error: str | None = None


@dataclass
class DepsStatus:
    manager: str = "unknown"
    status: str = "unknown"  # "ok" | "missing" | "stale" | "unknown"
    lockfile_path: str | None = None
    marker_path: str | None = None
    reason: str | None = None


@dataclass
class RegistryStatus:
    latest_version: str | None = None
    error: str | None = None


@dataclass
class NpmTagStatus:
    tag: str = ""
    version: str | None = None
    error: str | None = None


@dataclass
class UpdateCheckResult:
    root: str | None = None
    install_kind: str = "unknown"  # "git" | "package" | "unknown"
    package_manager: str = "unknown"
    git: GitUpdateStatus | None = None
    deps: DepsStatus | None = None
    registry: RegistryStatus | None = None


# ─── semver comparison ───

@dataclass
class _ComparableSemver:
    major: int = 0
    minor: int = 0
    patch: int = 0
    prerelease: list[str] | None = None


def _normalize_legacy_dot_beta(version: str) -> str:
    trimmed = version.strip()
    match = re.match(r'^([vV]?[0-9]+\.[0-9]+\.[0-9]+)\.beta(?:\.([0-9A-Za-z.-]+))?$', trimmed)
    if not match:
        return trimmed
    base = match.group(1)
    suffix = match.group(2)
    return f"{base}-beta.{suffix}" if suffix else f"{base}-beta"


def _parse_comparable_semver(version: str | None) -> _ComparableSemver | None:
    if not version:
        return None
    normalized = _normalize_legacy_dot_beta(version.strip())
    match = re.match(
        r'^v?([0-9]+)\.([0-9]+)\.([0-9]+)(?:-([0-9A-Za-z._-]+))?(?:\+[0-9A-Za-z._-]+)?$',
        normalized,
    )
    if not match:
        return None
    major, minor, patch = int(match.group(1)), int(match.group(2)), int(match.group(3))
    prerelease_raw = match.group(4)
    prerelease = [p for p in prerelease_raw.split(".") if p] if prerelease_raw else None
    return _ComparableSemver(major=major, minor=minor, patch=patch, prerelease=prerelease)


def _compare_prerelease(a: list[str] | None, b: list[str] | None) -> int:
    if not a and not b:
        return 0
    if not a:
        return 1  # no prerelease > prerelease
    if not b:
        return -1
    max_len = max(len(a), len(b))
    for i in range(max_len):
        ai = a[i] if i < len(a) else None
        bi = b[i] if i < len(b) else None
        if ai is None and bi is None:
            return 0
        if ai is None:
            return -1
        if bi is None:
            return 1
        if ai == bi:
            continue
        ai_numeric = ai.isdigit()
        bi_numeric = bi.isdigit()
        if ai_numeric and bi_numeric:
            return -1 if int(ai) < int(bi) else 1
        if ai_numeric and not bi_numeric:
            return -1
        if not ai_numeric and bi_numeric:
            return 1
        return -1 if ai < bi else 1
    return 0


def compare_semver_strings(a: str | None, b: str | None) -> int | None:
    """Compare two semver strings. Returns -1, 0, or 1; None if unparseable."""
    pa = _parse_comparable_semver(a)
    pb = _parse_comparable_semver(b)
    if not pa or not pb:
        return None
    if pa.major != pb.major:
        return -1 if pa.major < pb.major else 1
    if pa.minor != pb.minor:
        return -1 if pa.minor < pb.minor else 1
    if pa.patch != pb.patch:
        return -1 if pa.patch < pb.patch else 1
    return _compare_prerelease(pa.prerelease, pb.prerelease)


def format_git_install_label(update: UpdateCheckResult) -> str | None:
    if update.install_kind != "git" or not update.git:
        return None
    short_sha = update.git.sha[:8] if update.git.sha else None
    branch = update.git.branch if update.git.branch and update.git.branch != "HEAD" else None
    tag = update.git.tag
    parts = [
        branch or ("detached" if tag else "git"),
        f"tag {tag}" if tag else None,
        f"@ {short_sha}" if short_sha else None,
    ]
    return " · ".join(p for p in parts if p)


# ─── git update checking ───

async def _run_git(args: list[str], cwd: str, timeout_s: float = 6.0) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_s,
        )
        return (proc.returncode or 0,
                stdout_bytes.decode(errors="replace").strip(),
                stderr_bytes.decode(errors="replace").strip())
    except (asyncio.TimeoutError, FileNotFoundError, OSError):
        return (-1, "", "git unavailable")


async def check_git_update_status(
    root: str,
    timeout_s: float = 6.0,
    fetch: bool = False,
) -> GitUpdateStatus:
    """Check git repository update status."""
    root = os.path.abspath(root)
    base = GitUpdateStatus(root=root)

    code, branch, stderr = await _run_git(["-C", root, "rev-parse", "--abbrev-ref", "HEAD"], root, timeout_s)
    if code != 0:
        base.error = stderr or "git unavailable"
        return base
    base.branch = branch or None

    code, sha, _ = await _run_git(["-C", root, "rev-parse", "HEAD"], root, timeout_s)
    base.sha = sha if code == 0 else None

    code, tag, _ = await _run_git(["-C", root, "describe", "--tags", "--exact-match"], root, timeout_s)
    base.tag = tag if code == 0 else None

    code, upstream, _ = await _run_git(["-C", root, "rev-parse", "--abbrev-ref", "@{upstream}"], root, timeout_s)
    base.upstream = upstream if code == 0 else None

    code, dirty_out, _ = await _run_git(["-C", root, "status", "--porcelain"], root, timeout_s)
    base.dirty = bool(dirty_out) if code == 0 else None

    if fetch:
        code, _, _ = await _run_git(["-C", root, "fetch", "--quiet", "--prune"], root, timeout_s)
        base.fetch_ok = code == 0

    if base.upstream:
        code, counts_out, _ = await _run_git(
            ["-C", root, "rev-list", "--left-right", "--count", f"HEAD...{base.upstream}"],
            root, timeout_s,
        )
        if code == 0 and counts_out:
            parts = counts_out.split()
            if len(parts) >= 2:
                try:
                    base.ahead = int(parts[0])
                    base.behind = int(parts[1])
                except ValueError:
                    pass

    return base


# ─── deps status checking ───

def _resolve_deps_marker(root: str, manager: str) -> tuple[str | None, str | None]:
    if manager == "pnpm":
        return os.path.join(root, "pnpm-lock.yaml"), os.path.join(root, "node_modules", ".modules.yaml")
    if manager == "bun":
        return os.path.join(root, "bun.lockb"), os.path.join(root, "node_modules")
    if manager == "npm":
        return os.path.join(root, "package-lock.json"), os.path.join(root, "node_modules")
    return None, None


async def check_deps_status(root: str, manager: str) -> DepsStatus:
    root = os.path.abspath(root)
    lockfile, marker = _resolve_deps_marker(root, manager)

    if not lockfile or not marker:
        return DepsStatus(manager=manager, status="unknown", reason="unknown package manager")

    if not os.path.exists(lockfile):
        return DepsStatus(manager=manager, status="unknown", lockfile_path=lockfile, marker_path=marker, reason="lockfile missing")

    if not os.path.exists(marker):
        return DepsStatus(manager=manager, status="missing", lockfile_path=lockfile, marker_path=marker, reason="node_modules marker missing")

    try:
        lock_stat = os.stat(lockfile)
        marker_stat = os.stat(marker)
        if lock_stat.st_mtime > marker_stat.st_mtime + 1.0:
            return DepsStatus(manager=manager, status="stale", lockfile_path=lockfile, marker_path=marker,
                            reason="lockfile newer than install marker")
    except OSError:
        return DepsStatus(manager=manager, status="unknown", lockfile_path=lockfile, marker_path=marker)

    return DepsStatus(manager=manager, status="ok", lockfile_path=lockfile, marker_path=marker)


# ─── npm registry queries ───

async def fetch_npm_tag_version(tag: str = "latest", timeout_s: float = 3.5) -> NpmTagStatus:
    """Fetch version for a given npm tag from the registry."""
    try:
        from ..network.core import fetch_with_timeout
        result = await fetch_with_timeout(
            f"https://registry.npmjs.org/openclaw/{tag}",
            timeout_s=max(0.25, timeout_s),
        )
        if not result.get("ok"):
            return NpmTagStatus(tag=tag, error=f"HTTP {result.get('status', 0)}")
        body = result.get("body", b"")
        if isinstance(body, bytes):
            data = json.loads(body)
        else:
            data = json.loads(body)
        version = data.get("version")
        return NpmTagStatus(tag=tag, version=version if isinstance(version, str) else None)
    except Exception as e:
        return NpmTagStatus(tag=tag, error=str(e))


async def fetch_npm_latest_version(timeout_s: float = 3.5) -> RegistryStatus:
    result = await fetch_npm_tag_version("latest", timeout_s)
    return RegistryStatus(latest_version=result.version, error=result.error)


async def resolve_npm_channel_tag(channel: UpdateChannel, timeout_s: float = 3.5) -> dict[str, Any]:
    """Resolve the best npm tag for a given update channel."""
    channel_tag = channel_to_npm_tag(channel)
    channel_status = await fetch_npm_tag_version(channel_tag, timeout_s)

    if channel != "beta":
        return {"tag": channel_tag, "version": channel_status.version}

    latest_status = await fetch_npm_tag_version("latest", timeout_s)
    if not latest_status.version:
        return {"tag": channel_tag, "version": channel_status.version}
    if not channel_status.version:
        return {"tag": "latest", "version": latest_status.version}

    cmp = compare_semver_strings(channel_status.version, latest_status.version)
    if cmp is not None and cmp < 0:
        return {"tag": "latest", "version": latest_status.version}
    return {"tag": channel_tag, "version": channel_status.version}


# ─── full update check ───

async def check_update_status(
    root: str | None = None,
    timeout_s: float = 6.0,
    fetch_git: bool = False,
    include_registry: bool = False,
) -> UpdateCheckResult:
    """Full update status check combining git, deps, and registry."""
    if not root:
        registry = await fetch_npm_latest_version(timeout_s) if include_registry else None
        return UpdateCheckResult(root=None, install_kind="unknown", package_manager="unknown", registry=registry)

    root = os.path.abspath(root)

    # Detect package manager
    from ..platform.detect import detect_package_manager
    pm = detect_package_manager(root)

    # Detect if git repo
    from ..fs.git import find_git_root as get_git_root
    git_root = get_git_root(root)
    is_git = git_root and os.path.abspath(git_root) == root

    install_kind = "git" if is_git else "package"
    git = await check_git_update_status(root, timeout_s, fetch_git) if is_git else None
    deps = await check_deps_status(root, pm)
    registry = await fetch_npm_latest_version(timeout_s) if include_registry else None

    return UpdateCheckResult(
        root=root,
        install_kind=install_kind,
        package_manager=pm,
        git=git,
        deps=deps,
        registry=registry,
    )


# ─── update-channels.ts: helpers ───

DEV_BRANCH = "main"


def is_beta_tag(tag: str) -> bool:
    return bool(re.match(r'^v?[0-9]+\.[0-9]+\.[0-9]+-beta', tag))


def is_stable_tag(tag: str) -> bool:
    return bool(re.match(r'^v?[0-9]+\.[0-9]+\.[0-9]+$', tag))


# ─── update-runner.ts ───

@dataclass
class UpdateStepResult:
    name: str = ""
    command: str = ""
    cwd: str = ""
    duration_ms: int = 0
    exit_code: int | None = None
    stdout_tail: str | None = None
    stderr_tail: str | None = None


@dataclass
class UpdateRunResult:
    status: str = "ok"  # "ok" | "error" | "skipped"
    mode: str = "unknown"  # "git" | "pnpm" | "bun" | "npm" | "unknown"
    root: str | None = None
    reason: str | None = None
    before_sha: str | None = None
    before_version: str | None = None
    after_sha: str | None = None
    after_version: str | None = None
    steps: list[UpdateStepResult] = field(default_factory=list)
    duration_ms: int = 0


@dataclass
class UpdateStepInfo:
    name: str = ""
    command: str = ""
    index: int = 0
    total: int = 0


from typing import Protocol

class UpdateStepProgressCallback(Protocol):
    def on_step_start(self, step: UpdateStepInfo) -> None: ...
    def on_step_complete(self, step: UpdateStepInfo, duration_ms: int, exit_code: int | None) -> None: ...


DEFAULT_UPDATE_TIMEOUT_MS = 20 * 60_000
MAX_UPDATE_LOG_CHARS = 8000
PREFLIGHT_MAX_COMMITS = 10


def _trim_log_tail(text: str, max_chars: int = MAX_UPDATE_LOG_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return "…" + text[-(max_chars - 1):]


def _manager_install_args(manager: str) -> list[str]:
    if manager == "pnpm":
        return ["pnpm", "install"]
    if manager == "bun":
        return ["bun", "install"]
    return ["npm", "install"]


def _manager_script_args(manager: str, script: str, args: list[str] | None = None) -> list[str]:
    extra = args or []
    if manager == "pnpm":
        return ["pnpm", script, *extra]
    if manager == "bun":
        return ["bun", "run", script, *extra]
    if extra:
        return ["npm", "run", script, "--", *extra]
    return ["npm", "run", script]


async def _run_step(
    name: str,
    argv: list[str],
    cwd: str,
    timeout_s: float = 600.0,
    env: dict[str, str] | None = None,
    progress: Any | None = None,
    step_index: int = 0,
    total_steps: int = 0,
) -> UpdateStepResult:
    """Run a single update step and return its result."""
    command = " ".join(argv)
    step_info = UpdateStepInfo(name=name, command=command, index=step_index, total=total_steps)

    if progress and hasattr(progress, 'on_step_start'):
        progress.on_step_start(step_info)

    import time
    started = time.time()

    try:
        full_env = {**os.environ, **(env or {})}
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            env=full_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout_s,
        )
        duration_ms = int((time.time() - started) * 1000)
        exit_code = proc.returncode

        result = UpdateStepResult(
            name=name,
            command=command,
            cwd=cwd,
            duration_ms=duration_ms,
            exit_code=exit_code,
            stdout_tail=_trim_log_tail(stdout_bytes.decode(errors="replace")),
            stderr_tail=_trim_log_tail(stderr_bytes.decode(errors="replace")),
        )
    except (asyncio.TimeoutError, FileNotFoundError, OSError) as e:
        duration_ms = int((time.time() - started) * 1000)
        result = UpdateStepResult(
            name=name, command=command, cwd=cwd,
            duration_ms=duration_ms, exit_code=-1,
            stderr_tail=str(e),
        )

    if progress and hasattr(progress, 'on_step_complete'):
        progress.on_step_complete(step_info, result.duration_ms, result.exit_code)

    return result


async def run_gateway_update(
    cwd: str | None = None,
    channel: UpdateChannel = "dev",
    timeout_s: float = 1200.0,
    progress: Any | None = None,
) -> UpdateRunResult:
    """Run gateway update process (git pull + deps + build, or npm update)."""
    import time
    started = time.time()
    steps: list[UpdateStepResult] = []
    step_index = 0

    root = cwd or os.getcwd()
    root = os.path.abspath(root)

    # Detect git root
    code, git_root_str, _ = await _run_git(["-C", root, "rev-parse", "--show-toplevel"], root, 4.0)
    git_root = git_root_str if code == 0 and git_root_str else None

    if not git_root:
        # Package-based update
        from ..platform.detect import detect_package_manager
        pm = detect_package_manager(root)
        install_argv = _manager_install_args(pm)
        result = await _run_step("install", install_argv, root, timeout_s, progress=progress)
        steps.append(result)
        return UpdateRunResult(
            status="ok" if result.exit_code == 0 else "error",
            mode=pm,
            root=root,
            steps=steps,
            duration_ms=int((time.time() - started) * 1000),
        )

    git_root = os.path.abspath(git_root)

    # Get before state
    code, before_sha, _ = await _run_git(["-C", git_root, "rev-parse", "HEAD"], git_root, 4.0)
    before_sha = before_sha if code == 0 else None

    # Clean check
    result = await _run_step(
        "clean check",
        ["git", "-C", git_root, "status", "--porcelain", "--", ":!dist/control-ui/"],
        git_root, 10.0, progress=progress, step_index=step_index, total_steps=10,
    )
    steps.append(result)
    step_index += 1

    if result.stdout_tail and result.stdout_tail.strip():
        return UpdateRunResult(
            status="skipped", mode="git", root=git_root, reason="dirty",
            before_sha=before_sha,
            steps=steps, duration_ms=int((time.time() - started) * 1000),
        )

    if channel == "dev":
        # Dev channel: fetch + rebase
        fetch_result = await _run_step(
            "git fetch",
            ["git", "-C", git_root, "fetch", "--all", "--prune", "--tags"],
            git_root, timeout_s, progress=progress, step_index=step_index, total_steps=10,
        )
        steps.append(fetch_result)
        step_index += 1

        if fetch_result.exit_code != 0:
            return UpdateRunResult(
                status="error", mode="git", root=git_root, reason="fetch-failed",
                before_sha=before_sha,
                steps=steps, duration_ms=int((time.time() - started) * 1000),
            )

        # Check upstream
        up_result = await _run_step(
            "upstream check",
            ["git", "-C", git_root, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
            git_root, 10.0, progress=progress, step_index=step_index, total_steps=10,
        )
        steps.append(up_result)
        step_index += 1

        if up_result.exit_code != 0:
            return UpdateRunResult(
                status="skipped", mode="git", root=git_root, reason="no-upstream",
                before_sha=before_sha,
                steps=steps, duration_ms=int((time.time() - started) * 1000),
            )

        # Rebase
        rebase_result = await _run_step(
            "git pull --rebase",
            ["git", "-C", git_root, "pull", "--rebase"],
            git_root, timeout_s, progress=progress, step_index=step_index, total_steps=10,
        )
        steps.append(rebase_result)
        step_index += 1

        if rebase_result.exit_code != 0:
            # Abort rebase
            abort_result = await _run_step(
                "git rebase --abort",
                ["git", "-C", git_root, "rebase", "--abort"],
                git_root, 30.0,
            )
            steps.append(abort_result)
            return UpdateRunResult(
                status="error", mode="git", root=git_root, reason="rebase-failed",
                before_sha=before_sha,
                steps=steps, duration_ms=int((time.time() - started) * 1000),
            )
    else:
        # Stable/beta channel: fetch + checkout tag
        fetch_result = await _run_step(
            "git fetch",
            ["git", "-C", git_root, "fetch", "--all", "--prune", "--tags"],
            git_root, timeout_s, progress=progress, step_index=step_index, total_steps=10,
        )
        steps.append(fetch_result)
        step_index += 1

        if fetch_result.exit_code != 0:
            return UpdateRunResult(
                status="error", mode="git", root=git_root, reason="fetch-failed",
                before_sha=before_sha,
                steps=steps, duration_ms=int((time.time() - started) * 1000),
            )

        # Find best tag for channel
        code, tags_out, _ = await _run_git(
            ["-C", git_root, "tag", "--list", "v*", "--sort=-v:refname"], git_root, 10.0,
        )
        tags = [t.strip() for t in tags_out.split("\n") if t.strip()] if code == 0 else []

        target_tag = None
        if channel == "beta":
            beta_tag = next((t for t in tags if is_beta_tag(t)), None)
            stable_tag = next((t for t in tags if is_stable_tag(t)), None)
            if not beta_tag:
                target_tag = stable_tag
            elif not stable_tag:
                target_tag = beta_tag
            else:
                cmp = compare_semver_strings(beta_tag, stable_tag)
                target_tag = stable_tag if (cmp is not None and cmp < 0) else beta_tag
        else:
            target_tag = next((t for t in tags if is_stable_tag(t)), None)

        if not target_tag:
            return UpdateRunResult(
                status="error", mode="git", root=git_root, reason="no-release-tag",
                before_sha=before_sha,
                steps=steps, duration_ms=int((time.time() - started) * 1000),
            )

        checkout_result = await _run_step(
            f"git checkout {target_tag}",
            ["git", "-C", git_root, "checkout", "--detach", target_tag],
            git_root, 30.0, progress=progress, step_index=step_index, total_steps=10,
        )
        steps.append(checkout_result)
        step_index += 1

        if checkout_result.exit_code != 0:
            return UpdateRunResult(
                status="error", mode="git", root=git_root, reason="checkout-failed",
                before_sha=before_sha,
                steps=steps, duration_ms=int((time.time() - started) * 1000),
            )

    # Deps install
    from ..platform.detect import detect_package_manager
    pm = detect_package_manager(git_root)
    deps_result = await _run_step(
        "deps install", _manager_install_args(pm), git_root, timeout_s,
        progress=progress, step_index=step_index, total_steps=10,
    )
    steps.append(deps_result)
    step_index += 1

    if deps_result.exit_code != 0:
        return UpdateRunResult(
            status="error", mode="git", root=git_root, reason="deps-install-failed",
            before_sha=before_sha,
            steps=steps, duration_ms=int((time.time() - started) * 1000),
        )

    # Build
    build_result = await _run_step(
        "build", _manager_script_args(pm, "build"), git_root, timeout_s,
        progress=progress, step_index=step_index, total_steps=10,
    )
    steps.append(build_result)
    step_index += 1

    if build_result.exit_code != 0:
        return UpdateRunResult(
            status="error", mode="git", root=git_root, reason="build-failed",
            before_sha=before_sha,
            steps=steps, duration_ms=int((time.time() - started) * 1000),
        )

    # Get after state
    code, after_sha, _ = await _run_git(["-C", git_root, "rev-parse", "HEAD"], git_root, 4.0)
    after_sha = after_sha if code == 0 else None

    return UpdateRunResult(
        status="ok", mode="git", root=git_root,
        before_sha=before_sha, after_sha=after_sha,
        steps=steps, duration_ms=int((time.time() - started) * 1000),
    )

