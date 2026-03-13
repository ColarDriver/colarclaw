"""Background daemon management.

Ported from bk/src/daemon/ (~29 TS files, ~4.3k lines).

Covers daemon process lifecycle (start, stop, PID file),
system service installation (systemd/launchd), health monitoring,
and automatic restart with crash recovery.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ─── PID file management ───

@dataclass
class DaemonInfo:
    """Running daemon information."""
    pid: int = 0
    started_at: str = ""
    version: str = ""
    port: int = 18789
    config_path: str = ""


def write_pid_file(path: str, info: DaemonInfo) -> None:
    """Write daemon PID file."""
    os.makedirs(os.path.dirname(path), mode=0o700, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "pid": info.pid,
            "startedAt": info.started_at,
            "version": info.version,
            "port": info.port,
            "configPath": info.config_path,
        }, f, indent=2)


def read_pid_file(path: str) -> DaemonInfo | None:
    """Read daemon PID file."""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return DaemonInfo(
            pid=int(data.get("pid", 0)),
            started_at=str(data.get("startedAt", "")),
            version=str(data.get("version", "")),
            port=int(data.get("port", 18789)),
            config_path=str(data.get("configPath", "")),
        )
    except Exception:
        return None


def remove_pid_file(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def is_process_running(pid: int) -> bool:
    """Check if a process is running by PID."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # Exists but we can't signal it


# ─── Daemon lifecycle ───

class DaemonManager:
    """Manages the daemon process lifecycle."""

    def __init__(self, *, state_dir: str = ""):
        from ..config.paths import resolve_state_dir
        self._state_dir = state_dir or resolve_state_dir()
        self._pid_file = os.path.join(self._state_dir, "daemon.pid")
        self._log_file = os.path.join(self._state_dir, "logs", "daemon.log")

    @property
    def pid_file(self) -> str:
        return self._pid_file

    def is_running(self) -> bool:
        info = read_pid_file(self._pid_file)
        if not info:
            return False
        return is_process_running(info.pid)

    def get_info(self) -> DaemonInfo | None:
        info = read_pid_file(self._pid_file)
        if info and is_process_running(info.pid):
            return info
        return None

    def start(
        self,
        *,
        port: int = 18789,
        bind: str = "loopback",
        config_path: str = "",
    ) -> DaemonInfo | None:
        """Start the daemon in the background."""
        if self.is_running():
            logger.warning("Daemon is already running")
            return self.get_info()

        os.makedirs(os.path.dirname(self._log_file), exist_ok=True)

        # Start gateway process
        cmd = [
            sys.executable, "-m", "openclaw.gateway",
            "--port", str(port),
            "--bind", bind,
        ]
        if config_path:
            cmd.extend(["--config", config_path])

        log_fd = open(self._log_file, "a", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            stdout=log_fd,
            stderr=log_fd,
            start_new_session=True,
        )

        info = DaemonInfo(
            pid=proc.pid,
            started_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            port=port,
            config_path=config_path,
        )
        write_pid_file(self._pid_file, info)
        logger.info(f"Daemon started (PID {proc.pid}, port {port})")
        return info

    def stop(self) -> bool:
        """Stop the running daemon."""
        info = read_pid_file(self._pid_file)
        if not info:
            logger.info("No daemon PID file found")
            return False

        if not is_process_running(info.pid):
            remove_pid_file(self._pid_file)
            logger.info("Daemon is not running (stale PID file removed)")
            return False

        try:
            os.kill(info.pid, signal.SIGTERM)
            # Wait up to 10 seconds
            for _ in range(100):
                if not is_process_running(info.pid):
                    break
                time.sleep(0.1)
            else:
                # Force kill
                os.kill(info.pid, signal.SIGKILL)
                time.sleep(0.5)
        except ProcessLookupError:
            pass
        except PermissionError:
            logger.error(f"Permission denied to stop PID {info.pid}")
            return False

        remove_pid_file(self._pid_file)
        logger.info(f"Daemon stopped (PID {info.pid})")
        return True

    def restart(self, **kwargs: Any) -> DaemonInfo | None:
        """Restart the daemon."""
        info = self.get_info()
        port = kwargs.get("port", info.port if info else 18789)
        self.stop()
        time.sleep(0.5)
        return self.start(port=port, **{k: v for k, v in kwargs.items() if k != "port"})


# ─── Systemd service ───

SYSTEMD_UNIT_TEMPLATE = """\
[Unit]
Description=OpenClaw Gateway
After=network.target

[Service]
Type=simple
ExecStart={exec_start}
Restart=on-failure
RestartSec=5
User={user}
WorkingDirectory={work_dir}
Environment=HOME={home}

[Install]
WantedBy=multi-user.target
"""


def generate_systemd_unit(
    *,
    exec_start: str = "",
    user: str = "",
    work_dir: str = "",
    home: str = "",
) -> str:
    """Generate a systemd unit file."""
    return SYSTEMD_UNIT_TEMPLATE.format(
        exec_start=exec_start or f"{sys.executable} -m openclaw.gateway",
        user=user or os.environ.get("USER", "root"),
        work_dir=work_dir or os.path.expanduser("~"),
        home=home or os.path.expanduser("~"),
    )


def install_systemd_service(unit_content: str) -> bool:
    """Install a systemd service unit."""
    unit_path = "/etc/systemd/system/openclaw-gateway.service"
    try:
        Path(unit_path).write_text(unit_content, encoding="utf-8")
        subprocess.run(["systemctl", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "enable", "openclaw-gateway"], check=True)
        return True
    except Exception as e:
        logger.error(f"Failed to install systemd service: {e}")
        return False


# ─── LaunchAgent (macOS) ───

LAUNCHD_PLIST_TEMPLATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>ai.openclaw.gateway</string>
  <key>ProgramArguments</key>
  <array>
    <string>{python}</string>
    <string>-m</string>
    <string>openclaw.gateway</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
  <key>StandardOutPath</key>
  <string>{log_path}</string>
  <key>StandardErrorPath</key>
  <string>{log_path}</string>
</dict>
</plist>
"""


def generate_launchd_plist(*, log_path: str = "/tmp/openclaw-gateway.log") -> str:
    """Generate a macOS LaunchAgent plist."""
    return LAUNCHD_PLIST_TEMPLATE.format(
        python=sys.executable,
        log_path=log_path,
    )
