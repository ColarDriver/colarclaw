"""Infra install — ported from bk/src/infra/install-flow.ts, install-from-npm-spec.ts,
install-mode-options.ts, install-package-dir.ts, install-safe-path.ts,
install-source-utils.ts, install-target.ts, npm-integrity.ts,
npm-pack-install.ts, npm-registry-spec.ts.

Plugin/package installation: flow orchestration, safe paths, npm registry,
integrity verification, package resolution, source detection.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("infra.install")


# ─── install-mode-options.ts ───

InstallMode = Literal["global", "local", "workspace"]


@dataclass
class InstallModeOptions:
    mode: str = "global"  # InstallMode
    global_dir: str | None = None
    workspace_dir: str | None = None
    force: bool = False
    omit_dev: bool = True


# ─── install-target.ts ───

@dataclass
class InstallTarget:
    name: str = ""
    version: str | None = None
    registry: str | None = None
    source: str = "npm"  # "npm" | "git" | "local" | "tarball"
    spec: str = ""  # full install spec e.g. "openclaw@latest"


def parse_install_spec(spec: str) -> InstallTarget:
    """Parse npm install spec like 'pkg@version'."""
    cleaned = spec.strip()
    if not cleaned:
        return InstallTarget()

    if cleaned.startswith("file:") or cleaned.startswith("/") or cleaned.startswith("./"):
        return InstallTarget(spec=cleaned, source="local")

    if cleaned.startswith("git+") or cleaned.endswith(".git"):
        return InstallTarget(spec=cleaned, source="git")

    if cleaned.endswith(".tgz") or cleaned.endswith(".tar.gz"):
        return InstallTarget(spec=cleaned, source="tarball")

    # npm spec: name@version
    if "@" in cleaned and not cleaned.startswith("@"):
        name, _, version = cleaned.partition("@")
        return InstallTarget(name=name, version=version or None, spec=cleaned)

    # scoped package: @scope/name@version
    if cleaned.startswith("@"):
        rest = cleaned[1:]
        if "@" in rest:
            scope_and_name, _, version = rest.rpartition("@")
            name = f"@{scope_and_name}"
            return InstallTarget(name=name, version=version or None, spec=cleaned)
        return InstallTarget(name=cleaned, spec=cleaned)

    return InstallTarget(name=cleaned, spec=cleaned)


# ─── install-safe-path.ts ───

_UNSAFE_PATH_CHARS = re.compile(r'[<>:"|?*\x00-\x1f]')
_TRAVERSAL_RE = re.compile(r'(^|[\\/])\.\.($|[\\/])')


def is_safe_install_path(path_str: str) -> bool:
    """Check if a path is safe for installation."""
    if not path_str or not path_str.strip():
        return False
    if _UNSAFE_PATH_CHARS.search(path_str):
        return False
    if _TRAVERSAL_RE.search(path_str):
        return False
    return True


def resolve_safe_install_dir(base_dir: str, name: str) -> str | None:
    """Resolve a safe installation directory."""
    safe_name = re.sub(r'[^a-zA-Z0-9._@/-]', '_', name)
    if not safe_name:
        return None
    full_path = os.path.join(base_dir, safe_name)
    abs_base = os.path.abspath(base_dir)
    abs_full = os.path.abspath(full_path)
    if not abs_full.startswith(abs_base + os.sep):
        return None
    return abs_full


# ─── install-package-dir.ts ───

def resolve_install_package_dir(
    name: str,
    mode: str = "global",
    global_dir: str | None = None,
    workspace_dir: str | None = None,
) -> str | None:
    """Resolve where a package should be installed."""
    if mode == "global":
        base = global_dir or os.path.join(str(Path.home()), ".openclaw", "extensions")
    elif mode == "workspace":
        if not workspace_dir:
            return None
        base = os.path.join(workspace_dir, "node_modules")
    else:
        base = os.path.join(str(Path.home()), ".openclaw", "extensions")

    return resolve_safe_install_dir(base, name)


def is_package_installed(install_dir: str) -> bool:
    """Check if a package is installed at the given directory."""
    return os.path.isfile(os.path.join(install_dir, "package.json"))


def read_installed_package_version(install_dir: str) -> str | None:
    """Read installed package version from package.json."""
    pkg_path = os.path.join(install_dir, "package.json")
    try:
        with open(pkg_path) as f:
            data = json.load(f)
        return data.get("version")
    except (OSError, json.JSONDecodeError):
        return None


# ─── install-source-utils.ts ───

def detect_install_source(spec: str) -> str:
    """Detect the source type of an install spec."""
    target = parse_install_spec(spec)
    return target.source


def is_npm_spec(spec: str) -> bool:
    return detect_install_source(spec) == "npm"


def is_local_spec(spec: str) -> bool:
    return detect_install_source(spec) == "local"


def is_git_spec(spec: str) -> bool:
    return detect_install_source(spec) == "git"


def normalize_npm_package_name(name: str) -> str:
    """Normalize npm package name (lowercase, trim)."""
    return name.strip().lower()


# ─── npm-registry-spec.ts ───

@dataclass
class NpmRegistrySpec:
    name: str = ""
    version: str | None = None
    tag: str | None = None
    registry_url: str = "https://registry.npmjs.org"


def resolve_npm_registry_url(name: str, version: str | None = None,
                              registry: str = "https://registry.npmjs.org") -> str:
    """Build npm registry URL for a package."""
    encoded = name.replace("/", "%2f")
    if version:
        return f"{registry.rstrip('/')}/{encoded}/{version}"
    return f"{registry.rstrip('/')}/{encoded}"


async def fetch_npm_package_metadata(name: str, registry: str = "https://registry.npmjs.org",
                                      timeout_s: float = 5.0) -> dict[str, Any] | None:
    """Fetch package metadata from npm registry."""
    try:
        from ..network.core import fetch_with_timeout
        url = resolve_npm_registry_url(name, registry=registry)
        result = await fetch_with_timeout(url, timeout_s=timeout_s)
        if not result.get("ok"):
            return None
        body = result.get("body", b"")
        return json.loads(body if isinstance(body, str) else body.decode(errors="replace"))
    except Exception:
        return None


# ─── npm-integrity.ts ───

def compute_integrity_hash(data: bytes, algorithm: str = "sha512") -> str:
    """Compute SRI integrity hash."""
    import base64
    h = hashlib.new(algorithm)
    h.update(data)
    digest = base64.b64encode(h.digest()).decode()
    return f"{algorithm}-{digest}"


def verify_integrity(data: bytes, expected: str) -> bool:
    """Verify data against SRI integrity string."""
    import base64
    if "-" not in expected:
        return False
    algo, _, expected_digest = expected.partition("-")
    try:
        h = hashlib.new(algo)
        h.update(data)
        actual_digest = base64.b64encode(h.digest()).decode()
        return actual_digest == expected_digest
    except (ValueError, Exception):
        return False


# ─── npm-pack-install.ts ───

async def npm_pack_install(
    spec: str,
    target_dir: str,
    omit_dev: bool = True,
    timeout_s: float = 60.0,
) -> dict[str, Any]:
    """Install a package using npm pack + npm install."""
    import asyncio
    os.makedirs(target_dir, exist_ok=True)

    # npm install
    args = ["npm", "install", spec]
    if omit_dev:
        args.append("--omit=dev")
    args.extend(["--prefix", target_dir])

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
            cwd=target_dir,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        return {
            "ok": proc.returncode == 0,
            "stdout": stdout.decode(errors="replace"),
            "stderr": stderr.decode(errors="replace"),
            "exit_code": proc.returncode,
        }
    except asyncio.TimeoutError:
        return {"ok": False, "error": "timeout", "exit_code": -1, "stdout": "", "stderr": ""}
    except Exception as e:
        return {"ok": False, "error": str(e), "exit_code": -1, "stdout": "", "stderr": ""}


# ─── install-flow.ts ───

@dataclass
class InstallFlowResult:
    ok: bool = False
    install_dir: str | None = None
    version: str | None = None
    error: str | None = None


async def run_install_flow(
    spec: str,
    options: InstallModeOptions | None = None,
) -> InstallFlowResult:
    """Run the full install flow for a package/plugin."""
    opts = options or InstallModeOptions()
    target = parse_install_spec(spec)

    if not target.name and target.source == "npm":
        return InstallFlowResult(ok=False, error="invalid install spec")

    install_dir = resolve_install_package_dir(
        target.name or spec,
        mode=opts.mode,
        global_dir=opts.global_dir,
        workspace_dir=opts.workspace_dir,
    )
    if not install_dir:
        return InstallFlowResult(ok=False, error="could not resolve install directory")

    result = await npm_pack_install(spec, install_dir, omit_dev=opts.omit_dev)
    if not result.get("ok"):
        return InstallFlowResult(
            ok=False,
            install_dir=install_dir,
            error=result.get("error") or result.get("stderr", "install failed"),
        )

    version = read_installed_package_version(install_dir)
    return InstallFlowResult(ok=True, install_dir=install_dir, version=version)


# ─── install-package-dir.ts: staged install ───

import shutil
import tempfile

INSTALL_BASE_CHANGED_ERROR = "install base directory changed during install"


def _is_relative_path_inside_base(rel: str) -> bool:
    return bool(rel) and rel != ".." and not rel.startswith(f"..{os.sep}")


def _assert_canonical_path_within_base(base_dir: str, candidate: str) -> None:
    """Assert that candidate resolves within base_dir."""
    real_base = os.path.realpath(base_dir)
    real_candidate = os.path.realpath(candidate)
    if not real_candidate.startswith(real_base + os.sep) and real_candidate != real_base:
        raise ValueError(f"path escape: {candidate} not within {base_dir}")


def _sanitize_manifest_for_npm_install(target_dir: str) -> None:
    """Remove workspace: devDependencies from package.json before npm install."""
    manifest_path = os.path.join(target_dir, "package.json")
    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)
    except (OSError, json.JSONDecodeError):
        return
    dev_deps = manifest.get("devDependencies")
    if not isinstance(dev_deps, dict):
        return
    filtered = {k: v for k, v in dev_deps.items()
                if not (isinstance(v, str) and v.strip().startswith("workspace:"))}
    if len(filtered) == len(dev_deps):
        return
    if not filtered:
        del manifest["devDependencies"]
    else:
        manifest["devDependencies"] = filtered
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")


async def install_package_dir(
    source_dir: str,
    target_dir: str,
    mode: str = "install",  # "install" | "update"
    timeout_s: float = 300.0,
    has_deps: bool = True,
    copy_error_prefix: str = "install failed",
    deps_log_message: str = "Installing dependencies...",
    after_copy: Any = None,
    log_fn: Any = None,
) -> dict[str, Any]:
    """Staged package directory install with backup/restore and boundary checks."""
    import asyncio

    install_base_dir = os.path.dirname(target_dir)
    os.makedirs(install_base_dir, exist_ok=True)

    install_base_real = os.path.realpath(install_base_dir)
    rel = os.path.relpath(os.path.abspath(target_dir), os.path.abspath(install_base_dir))
    if not _is_relative_path_inside_base(rel):
        return {"ok": False, "error": f"{copy_error_prefix}: invalid install target path"}

    canonical_target = os.path.join(install_base_real, rel)
    stage_dir: str | None = None
    backup_dir: str | None = None

    try:
        _assert_canonical_path_within_base(install_base_real, canonical_target)

        # Stage: copy source to temp
        stage_dir = tempfile.mkdtemp(
            prefix=".openclaw-install-stage-", dir=install_base_real
        )
        shutil.copytree(source_dir, stage_dir, dirs_exist_ok=True)

        # Post-copy hook
        if after_copy:
            await after_copy(stage_dir) if asyncio.iscoroutinefunction(after_copy) else after_copy(stage_dir)

        # Deps install
        if has_deps:
            _sanitize_manifest_for_npm_install(stage_dir)
            if log_fn:
                log_fn(deps_log_message)
            proc = await asyncio.create_subprocess_exec(
                "npm", "install", "--omit=dev", "--omit=peer", "--silent", "--ignore-scripts",
                cwd=stage_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
            if proc.returncode != 0:
                return {"ok": False, "error": f"npm install failed: {stderr.decode(errors='replace').strip()}"}

        # Backup existing if update
        if mode == "update" and os.path.exists(canonical_target):
            backup_root = os.path.join(install_base_real, ".openclaw-install-backups")
            os.makedirs(backup_root, exist_ok=True)
            backup_dir = os.path.join(
                backup_root, f"{os.path.basename(canonical_target)}-{int(time.time() * 1000)}"
            )
            # Verify base hasn't changed
            current_real = os.path.realpath(install_base_dir)
            if current_real != install_base_real:
                return {"ok": False, "error": INSTALL_BASE_CHANGED_ERROR}
            os.rename(canonical_target, backup_dir)

        # Publish: rename stage to target
        current_real = os.path.realpath(install_base_dir)
        if current_real != install_base_real:
            return {"ok": False, "error": INSTALL_BASE_CHANGED_ERROR}
        os.rename(stage_dir, canonical_target)
        stage_dir = None

        # Cleanup backup
        if backup_dir:
            shutil.rmtree(backup_dir, ignore_errors=True)

        return {"ok": True}

    except Exception as e:
        # Restore backup if available
        if backup_dir and os.path.exists(backup_dir):
            try:
                if os.path.exists(canonical_target):
                    shutil.rmtree(canonical_target, ignore_errors=True)
                os.rename(backup_dir, canonical_target)
            except OSError:
                pass
        if stage_dir:
            shutil.rmtree(stage_dir, ignore_errors=True)
        return {"ok": False, "error": f"{copy_error_prefix}: {e}"}


# ─── install-source-utils.ts: npm pack + resolution ───

@dataclass
class NpmSpecResolution:
    name: str | None = None
    version: str | None = None
    resolved_spec: str | None = None
    integrity: str | None = None
    shasum: str | None = None
    resolved_at: str | None = None


def _parse_npm_pack_json_output(raw: str) -> tuple[str | None, NpmSpecResolution]:
    """Parse npm pack --json output for filename and metadata."""
    trimmed = raw.strip()
    if not trimmed:
        return None, NpmSpecResolution()

    for candidate in [trimmed, trimmed[trimmed.find("["):] if "[" in trimmed else None]:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        entries = parsed if isinstance(parsed, list) else [parsed]
        fallback_filename = None
        fallback_meta = NpmSpecResolution()

        for entry in reversed(entries):
            if not isinstance(entry, dict):
                continue
            name = (entry.get("name") or "").strip() or None
            version = (entry.get("version") or "").strip() or None
            filename = (entry.get("filename") or "").strip() or None
            resolved_spec = f"{name}@{version}" if name and version else None
            meta = NpmSpecResolution(
                name=name, version=version, resolved_spec=resolved_spec,
                integrity=(entry.get("integrity") or "").strip() or None,
                shasum=(entry.get("shasum") or "").strip() or None,
            )
            if not fallback_filename:
                fallback_filename = filename
                fallback_meta = meta
            if filename:
                return filename, meta

        return fallback_filename, fallback_meta

    return None, NpmSpecResolution()


def _parse_packed_archive_from_stdout(stdout: str) -> str | None:
    """Extract .tgz filename from npm pack stdout."""
    lines = [l.strip() for l in stdout.splitlines() if l.strip()]
    for line in reversed(lines):
        match = re.search(r'([^\s"\']+\.tgz)', line)
        if match:
            return match.group(1)
    return None


async def pack_npm_spec_to_archive(
    spec: str,
    cwd: str,
    timeout_s: float = 300.0,
) -> dict[str, Any]:
    """Pack an npm spec to a local archive using npm pack."""
    import asyncio
    env = {**os.environ, "COREPACK_ENABLE_DOWNLOAD_PROMPT": "0", "NPM_CONFIG_IGNORE_SCRIPTS": "true"}
    try:
        proc = await asyncio.create_subprocess_exec(
            "npm", "pack", spec, "--ignore-scripts", "--json",
            cwd=cwd, env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
        stdout_str = stdout.decode(errors="replace")
        stderr_str = stderr.decode(errors="replace")

        if proc.returncode != 0:
            raw = stderr_str.strip() or stdout_str.strip()
            if re.search(r'E404|is not in this registry', raw, re.IGNORECASE):
                return {"ok": False, "error": f"Package not found on npm: {spec}"}
            return {"ok": False, "error": f"npm pack failed: {raw}"}

        filename, metadata = _parse_npm_pack_json_output(stdout_str)
        if not filename:
            filename = _parse_packed_archive_from_stdout(stdout_str)
        if not filename:
            # Try finding .tgz in cwd
            for f in os.listdir(cwd):
                if f.endswith(".tgz"):
                    filename = f
                    break
        if not filename:
            return {"ok": False, "error": "npm pack produced no archive"}

        archive_path = filename if os.path.isabs(filename) else os.path.join(cwd, filename)
        if not os.path.exists(archive_path):
            # Fallback: find any .tgz in cwd
            for f in os.listdir(cwd):
                if f.endswith(".tgz"):
                    archive_path = os.path.join(cwd, f)
                    break

        return {"ok": True, "archive_path": archive_path, "metadata": metadata}
    except asyncio.TimeoutError:
        return {"ok": False, "error": "npm pack timed out"}
    except Exception as e:
        return {"ok": False, "error": str(e)}

