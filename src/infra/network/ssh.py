"""Infra SSH — ported from bk/src/infra/ssh-config.ts, ssh-tunnel.ts,
scp-host.ts.

SSH config resolution, SSH tunneling, SCP host parsing.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("infra.ssh")


# ─── ssh-tunnel.ts: parsed target ───

@dataclass
class SshParsedTarget:
    user: str | None = None
    host: str = ""
    port: int = 22


def parse_ssh_target(target: str) -> SshParsedTarget:
    """Parse user@host:port into SshParsedTarget."""
    result = SshParsedTarget()
    cleaned = target.strip()
    if not cleaned:
        return result

    if "@" in cleaned:
        user_part, _, host_part = cleaned.partition("@")
        result.user = user_part.strip() or None
        cleaned = host_part

    if ":" in cleaned:
        host_part, _, port_part = cleaned.rpartition(":")
        result.host = host_part.strip()
        try:
            result.port = int(port_part.strip())
        except ValueError:
            result.host = cleaned
    else:
        result.host = cleaned.strip()

    return result


# ─── ssh-config.ts ───

@dataclass
class SshResolvedConfig:
    user: str | None = None
    host: str | None = None
    port: int | None = None
    identity_files: list[str] = field(default_factory=list)


def parse_ssh_config_output(output: str) -> SshResolvedConfig:
    """Parse output of `ssh -G host`."""
    result = SshResolvedConfig()
    for raw_line in output.split("\n"):
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) < 2:
            continue
        key, value = parts[0].lower(), parts[1].strip()
        if key == "user":
            result.user = value
        elif key == "hostname":
            result.host = value
        elif key == "port":
            try:
                port = int(value)
                if port > 0:
                    result.port = port
            except ValueError:
                pass
        elif key == "identityfile":
            if value != "none":
                result.identity_files.append(value)
    return result


async def resolve_ssh_config(
    target: SshParsedTarget,
    identity: str | None = None,
    timeout_s: float = 0.8,
) -> SshResolvedConfig | None:
    """Resolve effective SSH config for a target using `ssh -G`."""
    args = ["-G"]
    if target.port > 0 and target.port != 22:
        args.extend(["-p", str(target.port)])
    if identity and identity.strip():
        args.extend(["-i", identity.strip()])
    user_host = f"{target.user}@{target.host}" if target.user else target.host
    args.extend(["--", user_host])

    try:
        proc = await asyncio.create_subprocess_exec(
            "/usr/bin/ssh", *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout_bytes, _ = await asyncio.wait_for(
            proc.communicate(), timeout=max(0.2, timeout_s),
        )
        stdout = stdout_bytes.decode(errors="replace").strip()
        if proc.returncode != 0 or not stdout:
            return None
        return parse_ssh_config_output(stdout)
    except (asyncio.TimeoutError, FileNotFoundError, OSError):
        return None


# ─── ssh-tunnel.ts ───

@dataclass
class SshTunnel:
    local_port: int = 0
    remote_host: str = "localhost"
    remote_port: int = 0
    ssh_target: SshParsedTarget = field(default_factory=SshParsedTarget)
    process: asyncio.subprocess.Process | None = None
    running: bool = False

    async def start(self, identity: str | None = None, timeout_s: float = 10.0) -> bool:
        """Start SSH tunnel."""
        args = [
            "-N", "-L",
            f"{self.local_port}:{self.remote_host}:{self.remote_port}",
        ]
        if self.ssh_target.port > 0 and self.ssh_target.port != 22:
            args.extend(["-p", str(self.ssh_target.port)])
        if identity:
            args.extend(["-i", identity])
        user_host = (f"{self.ssh_target.user}@{self.ssh_target.host}"
                     if self.ssh_target.user else self.ssh_target.host)
        args.append(user_host)

        try:
            self.process = await asyncio.create_subprocess_exec(
                "ssh", *args,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            self.running = True
            return True
        except (FileNotFoundError, OSError) as e:
            logger.error(f"SSH tunnel failed: {e}")
            return False

    async def stop(self) -> None:
        if self.process:
            try:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except (asyncio.TimeoutError, ProcessLookupError):
                try:
                    self.process.kill()
                except ProcessLookupError:
                    pass
            self.running = False


def create_ssh_tunnel(
    local_port: int,
    remote_port: int,
    ssh_target: str | SshParsedTarget,
    remote_host: str = "localhost",
) -> SshTunnel:
    """Create an SSH tunnel (not started yet)."""
    if isinstance(ssh_target, str):
        ssh_target = parse_ssh_target(ssh_target)
    return SshTunnel(
        local_port=local_port,
        remote_host=remote_host,
        remote_port=remote_port,
        ssh_target=ssh_target,
    )


# ─── scp-host.ts ───

@dataclass
class ScpHost:
    user: str | None = None
    host: str = ""
    path: str = ""


def parse_scp_target(target: str) -> ScpHost:
    """Parse SCP target: [user@]host:path"""
    cleaned = target.strip()
    result = ScpHost()

    if "@" in cleaned:
        user_part, _, rest = cleaned.partition("@")
        result.user = user_part.strip() or None
        cleaned = rest

    if ":" in cleaned:
        host_part, _, path_part = cleaned.partition(":")
        result.host = host_part.strip()
        result.path = path_part.strip()
    else:
        result.host = cleaned.strip()

    return result


def format_scp_target(host: ScpHost) -> str:
    """Format ScpHost back to scp target string."""
    parts = []
    if host.user:
        parts.append(f"{host.user}@{host.host}")
    else:
        parts.append(host.host)
    if host.path:
        parts.append(f":{host.path}")
    return "".join(parts)
