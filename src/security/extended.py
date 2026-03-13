"""Security — extended: audit system, skill scanner, ACL fixes.

Ported from bk/src/security/ remaining:
audit-extra.sync.ts (~1349行), audit-extra.async.ts (~1314行),
audit.ts (~1253行), audit-channel.ts (~725行),
skill-scanner.ts (~583行), fix.ts (~477行),
windows-acl.ts (~363行).
"""
from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ─── Extended audit system ───

@dataclass
class AuditFinding:
    """A security audit finding."""
    id: str = ""
    severity: str = "info"  # "info" | "low" | "medium" | "high" | "critical"
    category: str = ""  # "config" | "permissions" | "network" | "exec" | "channel"
    title: str = ""
    description: str = ""
    path: str = ""
    fix_available: bool = False
    fix_description: str = ""


class SecurityAuditor:
    """Runs comprehensive security audits."""

    def __init__(self, config: dict[str, Any]):
        self._config = config
        self._findings: list[AuditFinding] = []

    @property
    def findings(self) -> list[AuditFinding]:
        return self._findings

    async def run_full_audit(self) -> list[AuditFinding]:
        """Run all security audit checks."""
        self._findings.clear()
        self._audit_config()
        self._audit_permissions()
        self._audit_network()
        self._audit_exec()
        await self._audit_channels()
        return self._findings

    def _audit_config(self) -> None:
        """Audit configuration security."""
        # Check for plaintext API keys in config
        config_str = str(self._config)
        if re.search(r'sk-ant-[a-zA-Z0-9_-]{20,}', config_str):
            self._findings.append(AuditFinding(
                id="config-plaintext-key", severity="high", category="config",
                title="Plaintext API key in config",
                description="API key should use environment variable or secret store",
                fix_available=True,
                fix_description="Use ${ENV_VAR} syntax or 1Password reference",
            ))

        # Check sandbox mode
        sec = self._config.get("security", {}) or {}
        if sec.get("allowBash", False) and not sec.get("sandboxMode"):
            self._findings.append(AuditFinding(
                id="config-bash-no-sandbox", severity="medium", category="config",
                title="Bash execution enabled without sandbox",
                description="Consider enabling sandbox mode when bash is allowed",
            ))

        # Check rate limiting
        if not sec.get("rateLimitEnabled", True):
            self._findings.append(AuditFinding(
                id="config-no-rate-limit", severity="low", category="config",
                title="Rate limiting disabled",
                description="Rate limiting provides protection against abuse",
            ))

    def _audit_permissions(self) -> None:
        """Audit file permissions."""
        from ..config.paths import resolve_state_dir
        state_dir = resolve_state_dir()
        
        # Check state dir permissions
        if os.path.isdir(state_dir):
            stat = os.stat(state_dir)
            mode = stat.st_mode & 0o777
            if mode & 0o077:
                self._findings.append(AuditFinding(
                    id="perm-state-dir", severity="medium", category="permissions",
                    title="State directory too permissive",
                    description=f"Mode {oct(mode)}; should be 0700",
                    path=state_dir, fix_available=True,
                    fix_description=f"chmod 700 {state_dir}",
                ))
        
        # Check config file permissions
        from ..config.paths import resolve_config_path
        config_path = resolve_config_path()
        if os.path.exists(config_path):
            stat = os.stat(config_path)
            mode = stat.st_mode & 0o777
            if mode & 0o077:
                self._findings.append(AuditFinding(
                    id="perm-config-file", severity="medium", category="permissions",
                    title="Config file too permissive",
                    description=f"Mode {oct(mode)}; should be 0600",
                    path=config_path, fix_available=True,
                    fix_description=f"chmod 600 {config_path}",
                ))

    def _audit_network(self) -> None:
        """Audit network configuration."""
        gateway = self._config.get("gateway", {}) or {}
        bind = gateway.get("bind", "loopback")
        if bind in ("0.0.0.0", "all"):
            self._findings.append(AuditFinding(
                id="net-public-bind", severity="high", category="network",
                title="Gateway bound to all interfaces",
                description="Gateway is accessible from any network",
                fix_available=True,
                fix_description="Set gateway.bind to 'loopback' or 'tailscale'",
            ))

        # Check CORS
        sec = self._config.get("security", {}) or {}
        cors = sec.get("corsOrigins", [])
        if "*" in cors:
            self._findings.append(AuditFinding(
                id="net-cors-wildcard", severity="medium", category="network",
                title="CORS allows all origins",
                description="Wildcard CORS can expose the API to cross-site attacks",
            ))

    def _audit_exec(self) -> None:
        """Audit exec approval settings."""
        approvals = self._config.get("approvals", {}) or {}
        if approvals.get("mode") == "none":
            self._findings.append(AuditFinding(
                id="exec-no-approval", severity="high", category="exec",
                title="No exec approval required",
                description="All tool executions will run without user approval",
            ))

    async def _audit_channels(self) -> None:
        """Audit channel configurations."""
        channels = self._config.get("channels", {}) or {}
        for name, cfg in channels.items():
            if not isinstance(cfg, dict):
                continue
            if not cfg.get("allowlist") and not cfg.get("allowedUsers") and not cfg.get("allowedChats"):
                self._findings.append(AuditFinding(
                    id=f"channel-no-allowlist-{name}", severity="medium",
                    category="channel",
                    title=f"No allowlist for {name} channel",
                    description="Without an allowlist, anyone can interact with the bot",
                ))


# ─── Skill scanner ───

@dataclass
class SkillScanResult:
    skill_path: str = ""
    is_safe: bool = True
    warnings: list[str] = field(default_factory=list)
    dangerous_patterns: list[str] = field(default_factory=list)


DANGEROUS_PATTERNS = [
    (re.compile(r"eval\s*\("), "eval() usage"),
    (re.compile(r"exec\s*\("), "exec() usage"),
    (re.compile(r"__import__\s*\("), "__import__() usage"),
    (re.compile(r"subprocess\.\s*(?:call|run|Popen)\s*\(.*shell\s*=\s*True"), "Shell injection risk"),
    (re.compile(r"os\.system\s*\("), "os.system() usage"),
    (re.compile(r"(?:rm\s+-rf|format\s+[cC]:)"), "Destructive command"),
]


def scan_skill(skill_dir: str) -> SkillScanResult:
    """Scan a skill directory for security issues."""
    result = SkillScanResult(skill_path=skill_dir)
    
    if not os.path.isdir(skill_dir):
        return result
    
    for root, _, files in os.walk(skill_dir):
        for filename in files:
            if not filename.endswith((".py", ".sh", ".js", ".ts")):
                continue
            filepath = os.path.join(root, filename)
            try:
                with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
                for pattern, desc in DANGEROUS_PATTERNS:
                    if pattern.search(content):
                        result.is_safe = False
                        result.dangerous_patterns.append(f"{os.path.basename(filepath)}: {desc}")
            except Exception:
                result.warnings.append(f"Could not scan {filename}")
    
    return result


# ─── Permission fix ───

def fix_permissions(path: str, *, mode: int = 0o600, recursive: bool = False) -> int:
    """Fix file permissions. Returns number of files fixed."""
    count = 0
    if os.path.isfile(path):
        current = os.stat(path).st_mode & 0o777
        if current != mode:
            os.chmod(path, mode)
            count += 1
    elif os.path.isdir(path) and recursive:
        dir_mode = mode | 0o100  # Add execute for directories
        os.chmod(path, dir_mode)
        count += 1
        for root, dirs, files in os.walk(path):
            for d in dirs:
                dp = os.path.join(root, d)
                os.chmod(dp, dir_mode)
                count += 1
            for f in files:
                fp = os.path.join(root, f)
                os.chmod(fp, mode)
                count += 1
    return count


def auto_fix_findings(findings: list[AuditFinding]) -> list[str]:
    """Automatically fix findings that have available fixes."""
    fixed = []
    for finding in findings:
        if not finding.fix_available:
            continue
        if finding.category == "permissions" and finding.path:
            target_mode = 0o700 if os.path.isdir(finding.path) else 0o600
            try:
                os.chmod(finding.path, target_mode)
                fixed.append(f"Fixed: {finding.title}")
            except Exception as e:
                logger.warning(f"Could not fix {finding.id}: {e}")
    return fixed
