"""Skill installation for ColarCore — based on openclaw/src/agents/skills-install.ts.

Handles executing install commands (brew, node/npm, go, uv, pip) for skills
that declare install specs in their SKILL.md frontmatter.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from dataclasses import dataclass, field

from .types import SkillInstallSpec


@dataclass
class SkillInstallResult:
    """Result of a skill installation attempt."""
    ok: bool
    message: str
    stdout: str = ""
    stderr: str = ""
    code: int | None = None
    warnings: list[str] = field(default_factory=list)


def has_binary(name: str) -> bool:
    """Check if a binary is available on the system PATH."""
    return shutil.which(name) is not None


def _resolve_brew_executable() -> str | None:
    """Try to find the Homebrew executable."""
    if has_binary("brew"):
        return "brew"
    # Common macOS / Linux Homebrew paths
    for candidate in ["/opt/homebrew/bin/brew", "/usr/local/bin/brew",
                      "/home/linuxbrew/.linuxbrew/bin/brew"]:
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _build_install_command(spec: SkillInstallSpec) -> tuple[list[str] | None, str | None]:
    """Build the install command for a given spec. Returns (argv, error)."""
    kind = spec.kind
    if kind == "brew":
        formula = spec.formula
        if not formula:
            return None, "missing brew formula"
        return ["brew", "install", formula], None
    elif kind == "node":
        package = spec.package
        if not package:
            return None, "missing node package"
        # Use npm by default; could be extended to support pnpm/yarn/bun
        return ["npm", "install", "-g", "--ignore-scripts", package], None
    elif kind == "go":
        module = spec.module
        if not module:
            return None, "missing go module"
        return ["go", "install", module], None
    elif kind == "uv":
        package = spec.package
        if not package:
            return None, "missing uv package"
        return ["uv", "tool", "install", package], None
    elif kind == "pip":
        package = spec.package
        if not package:
            return None, "missing pip package"
        return ["pip", "install", package], None
    elif kind == "download":
        return None, "download install not yet supported"
    else:
        return None, f"unsupported installer kind: {kind}"


def _run_command_sync(
    argv: list[str],
    timeout_seconds: int = 300,
    env: dict[str, str] | None = None,
) -> tuple[int | None, str, str]:
    """Run a command synchronously, returning (code, stdout, stderr)."""
    run_env = None
    if env:
        run_env = {**os.environ, **env}
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=run_env,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except FileNotFoundError:
        return None, "", f"command not found: {argv[0]}"
    except subprocess.TimeoutExpired:
        return None, "", f"command timed out after {timeout_seconds}s"
    except Exception as e:
        return None, "", str(e)


def _resolve_install_id(spec: SkillInstallSpec, index: int) -> str:
    """Compute the install ID for a spec, mirroring openclaw's resolveInstallId."""
    if spec.id:
        return spec.id.strip()
    return f"{spec.kind}-{index}"


def install_skill(
    *,
    skill_name: str,
    install_id: str,
    install_specs: list[SkillInstallSpec],
    timeout_ms: int = 300_000,
) -> SkillInstallResult:
    """Execute the install command for a skill.

    Finds the matching install spec by *install_id*, builds the command,
    and runs it.  Returns a result with ok/message/stdout/stderr.

    Mirrors openclaw's ``installSkill()`` in ``src/agents/skills-install.ts``.
    """
    timeout_s = max(1, min(timeout_ms // 1000, 900))

    # Find the matching install spec
    spec: SkillInstallSpec | None = None
    for i, s in enumerate(install_specs):
        if _resolve_install_id(s, i) == install_id:
            spec = s
            break

    if spec is None:
        return SkillInstallResult(
            ok=False,
            message=f"Installer not found: {install_id}",
        )

    # For brew installs, check that Homebrew is available
    brew_exe: str | None = None
    if spec.kind == "brew":
        brew_exe = _resolve_brew_executable()
        if not brew_exe:
            is_linux = platform.system() == "Linux"
            formula = spec.formula or "this package"
            if is_linux:
                hint = (
                    f'Homebrew is not installed. Install it from https://brew.sh '
                    f'or install "{formula}" manually using your system package manager '
                    f'(e.g. apt, dnf, pacman).'
                )
            else:
                hint = "Homebrew is not installed. Install it from https://brew.sh"
            return SkillInstallResult(
                ok=False,
                message=f"brew not installed — {hint}",
            )

    # For uv installs, check that uv is available; try brew-installing it if not
    if spec.kind == "uv" and not has_binary("uv"):
        if not brew_exe:
            brew_exe = _resolve_brew_executable()
        if brew_exe:
            code, stdout, stderr = _run_command_sync([brew_exe, "install", "uv"], timeout_s)
            if code != 0:
                return SkillInstallResult(
                    ok=False,
                    message="Failed to install uv (brew)",
                    stdout=stdout.strip(),
                    stderr=stderr.strip(),
                    code=code,
                )
        else:
            return SkillInstallResult(
                ok=False,
                message="uv not installed — install manually: https://docs.astral.sh/uv/getting-started/installation/",
            )

    # For go installs, check that go is available
    if spec.kind == "go" and not has_binary("go"):
        if not brew_exe:
            brew_exe = _resolve_brew_executable()
        if brew_exe:
            code, stdout, stderr = _run_command_sync([brew_exe, "install", "go"], timeout_s)
            if code != 0:
                return SkillInstallResult(
                    ok=False,
                    message="Failed to install go (brew)",
                    stdout=stdout.strip(),
                    stderr=stderr.strip(),
                    code=code,
                )
        else:
            return SkillInstallResult(
                ok=False,
                message="go not installed — install manually: https://go.dev/doc/install",
            )

    # Build the command
    argv, error = _build_install_command(spec)
    if error or not argv:
        return SkillInstallResult(
            ok=False,
            message=error or "invalid install command",
        )

    # Replace 'brew' with the resolved executable path
    if spec.kind == "brew" and brew_exe and argv[0] == "brew":
        argv[0] = brew_exe

    # Extra env for go installs (set GOBIN to brew bin dir)
    extra_env: dict[str, str] | None = None
    if spec.kind == "go" and brew_exe:
        try:
            code, stdout, _ = _run_command_sync([brew_exe, "--prefix"], min(timeout_s, 30))
            if code == 0 and stdout.strip():
                extra_env = {"GOBIN": os.path.join(stdout.strip(), "bin")}
        except Exception:
            pass

    # Execute
    code, stdout, stderr = _run_command_sync(argv, timeout_s, extra_env)
    if code == 0:
        return SkillInstallResult(
            ok=True,
            message="Installed",
            stdout=stdout.strip(),
            stderr=stderr.strip(),
            code=code,
        )

    # Build failure message
    failure_msg = f"Install failed (exit {code})"
    if stderr.strip():
        # Take the last meaningful line from stderr as the summary
        lines = [l.strip() for l in stderr.strip().splitlines() if l.strip()]
        if lines:
            failure_msg = lines[-1]
    return SkillInstallResult(
        ok=False,
        message=failure_msg,
        stdout=stdout.strip(),
        stderr=stderr.strip(),
        code=code,
    )
