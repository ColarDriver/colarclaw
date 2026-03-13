"""Infra doctor — ported from bk/src/infra/doctor-*.ts files.

Gateway diagnostics: health checks, configuration validation,
connectivity probes, dependency verification, fix suggestions.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger("infra.doctor")


# ─── doctor types ───

@dataclass
class DoctorCheckResult:
    name: str = ""
    passed: bool = True
    message: str = ""
    severity: str = "info"  # "info" | "warn" | "error"
    fix_hint: str | None = None


@dataclass
class DoctorReport:
    checks: list[DoctorCheckResult] = field(default_factory=list)
    passed: int = 0
    failed: int = 0
    warnings: int = 0
    summary: str = ""


# ─── doctor checks ───

def check_python_version(min_version: tuple[int, int] = (3, 10)) -> DoctorCheckResult:
    """Check Python version is sufficient."""
    version = sys.version_info[:2]
    if version >= min_version:
        return DoctorCheckResult(
            name="python_version", passed=True,
            message=f"Python {version[0]}.{version[1]} (>= {min_version[0]}.{min_version[1]})",
        )
    return DoctorCheckResult(
        name="python_version", passed=False, severity="error",
        message=f"Python {version[0]}.{version[1]} < {min_version[0]}.{min_version[1]}",
        fix_hint=f"Upgrade Python to {min_version[0]}.{min_version[1]} or later",
    )


def check_binary_available(name: str) -> DoctorCheckResult:
    """Check if a binary is available on PATH."""
    path = shutil.which(name)
    if path:
        return DoctorCheckResult(
            name=f"binary_{name}", passed=True,
            message=f"{name} found at {path}",
        )
    return DoctorCheckResult(
        name=f"binary_{name}", passed=False, severity="warn",
        message=f"{name} not found on PATH",
        fix_hint=f"Install {name} or add it to your PATH",
    )


def check_directory_writable(path: str) -> DoctorCheckResult:
    """Check if a directory is writable."""
    if not os.path.exists(path):
        return DoctorCheckResult(
            name=f"dir_writable_{os.path.basename(path)}", passed=True,
            message=f"Directory {path} does not exist (will be created)",
        )
    if os.access(path, os.W_OK):
        return DoctorCheckResult(
            name=f"dir_writable_{os.path.basename(path)}", passed=True,
            message=f"Directory {path} is writable",
        )
    return DoctorCheckResult(
        name=f"dir_writable_{os.path.basename(path)}", passed=False, severity="error",
        message=f"Directory {path} is not writable",
        fix_hint=f"Fix permissions: chmod u+w {path}",
    )


def check_env_var(key: str, required: bool = False) -> DoctorCheckResult:
    """Check if an environment variable is set."""
    value = os.environ.get(key, "").strip()
    if value:
        from .security import mask_api_key, is_credential_env_key
        display = mask_api_key(value) if is_credential_env_key(key) else value[:50]
        return DoctorCheckResult(
            name=f"env_{key}", passed=True,
            message=f"{key}={display}",
        )
    if required:
        return DoctorCheckResult(
            name=f"env_{key}", passed=False, severity="error",
            message=f"{key} is not set",
            fix_hint=f"Set {key} in your environment or .env file",
        )
    return DoctorCheckResult(
        name=f"env_{key}", passed=True, severity="info",
        message=f"{key} is not set (optional)",
    )


async def check_port_available(port: int, host: str = "127.0.0.1") -> DoctorCheckResult:
    """Check if a port is available."""
    from ..network.ports import is_port_available, inspect_port
    if is_port_available(port, host):
        return DoctorCheckResult(
            name=f"port_{port}", passed=True,
            message=f"Port {port} is available",
        )
    info = inspect_port(port)
    detail = f" (used by {info.process_name or '?'} pid={info.pid or '?'})" if info else ""
    return DoctorCheckResult(
        name=f"port_{port}", passed=False, severity="error",
        message=f"Port {port} is in use{detail}",
        fix_hint=f"Free port {port} or choose a different port",
    )


async def check_network_connectivity(url: str = "https://api.anthropic.com",
                                      timeout_s: float = 5.0) -> DoctorCheckResult:
    """Check network connectivity to a URL."""
    try:
        from ..network.core import fetch_with_timeout
        result = await fetch_with_timeout(url, timeout_s=timeout_s, method="HEAD")
        status = result.get("status", 0)
        if status > 0:
            return DoctorCheckResult(
                name=f"network_{url}", passed=True,
                message=f"Network connectivity to {url} OK (HTTP {status})",
            )
        return DoctorCheckResult(
            name=f"network_{url}", passed=False, severity="warn",
            message=f"Could not reach {url}",
        )
    except Exception as e:
        return DoctorCheckResult(
            name=f"network_{url}", passed=False, severity="warn",
            message=f"Network check failed for {url}: {e}",
            fix_hint="Check your network connection and firewall settings",
        )


# ─── run all checks ───

async def run_doctor(
    gateway_port: int = 18789,
    extra_checks: list[Callable[[], DoctorCheckResult]] | None = None,
) -> DoctorReport:
    """Run all doctor checks and generate report."""
    report = DoctorReport()

    # Sync checks
    sync_checks = [
        check_python_version(),
        check_binary_available("git"),
        check_directory_writable(os.path.join(str(__import__("pathlib").Path.home()), ".openclaw")),
        check_env_var("ANTHROPIC_API_KEY"),
        check_env_var("OPENAI_API_KEY"),
        check_env_var("GEMINI_API_KEY"),
    ]
    report.checks.extend(sync_checks)

    # Async checks
    async_results = await asyncio.gather(
        check_port_available(gateway_port),
        check_network_connectivity("https://api.anthropic.com"),
        return_exceptions=True,
    )
    for result in async_results:
        if isinstance(result, DoctorCheckResult):
            report.checks.append(result)
        elif isinstance(result, Exception):
            report.checks.append(DoctorCheckResult(
                name="async_check", passed=False, severity="warn",
                message=f"Check failed: {result}",
            ))

    # Extra checks
    if extra_checks:
        for check_fn in extra_checks:
            try:
                report.checks.append(check_fn())
            except Exception as e:
                report.checks.append(DoctorCheckResult(
                    name="extra_check", passed=False, severity="warn",
                    message=f"Extra check failed: {e}",
                ))

    # Summarize
    for check in report.checks:
        if check.passed:
            report.passed += 1
        elif check.severity == "warn":
            report.warnings += 1
        else:
            report.failed += 1

    total = len(report.checks)
    report.summary = f"{report.passed}/{total} passed, {report.failed} failed, {report.warnings} warnings"
    return report


def format_doctor_report(report: DoctorReport) -> str:
    """Format doctor report for display."""
    lines: list[str] = ["OpenClaw Doctor Report", "=" * 40]
    for check in report.checks:
        icon = "✓" if check.passed else ("⚠" if check.severity == "warn" else "✗")
        lines.append(f"  {icon} {check.message}")
        if check.fix_hint and not check.passed:
            lines.append(f"    → {check.fix_hint}")
    lines.append("")
    lines.append(report.summary)
    return "\n".join(lines)
