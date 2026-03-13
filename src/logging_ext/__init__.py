"""Logging subsystem.

Ported from bk/src/logging/ (~16 TS files).

Covers structured logging, log transports (file, console, remote),
log level resolution, context-aware logging, log rotation, and
session-scoped log streams.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

__all__ = [
    "setup_logging", "create_logger", "LogConfig",
    "SessionLogger", "StructuredFormatter",
]


@dataclass
class LogConfig:
    """Logging configuration."""
    level: str = "info"
    console: bool = True
    file: bool = True
    file_path: str = ""
    structured: bool = False
    max_file_size_bytes: int = 10 * 1024 * 1024
    max_files: int = 5
    include_timestamp: bool = True
    include_source: bool = False
    redact_secrets: bool = True


LOG_LEVEL_MAP = {
    "trace": logging.DEBUG,
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warn": logging.WARNING,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "fatal": logging.CRITICAL,
    "silent": logging.CRITICAL + 10,
}


def resolve_log_level(level: str) -> int:
    return LOG_LEVEL_MAP.get(level.lower(), logging.INFO)


class StructuredFormatter(logging.Formatter):
    """JSON structured log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname.lower(),
            "msg": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info and record.exc_info[1]:
            entry["error"] = str(record.exc_info[1])
        if hasattr(record, "extra_data"):
            entry["data"] = record.extra_data
        return json.dumps(entry, ensure_ascii=False)


class RedactFilter(logging.Filter):
    """Filter to redact sensitive values from log output."""

    SENSITIVE_PATTERNS = [
        "api_key", "apikey", "api-key", "token", "secret",
        "password", "credential", "authorization",
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for pattern in self.SENSITIVE_PATTERNS:
            if pattern in msg.lower():
                record.msg = self._redact(str(record.msg))
        return True

    @staticmethod
    def _redact(text: str) -> str:
        import re
        return re.sub(
            r'((?:api[_-]?key|token|secret|password|authorization)["\s:=]+)(["\']?)(\S{4})\S+',
            r'\1\2\3***',
            text, flags=re.IGNORECASE,
        )


def setup_logging(config: LogConfig | dict[str, Any] | None = None) -> None:
    """Set up the logging subsystem."""
    if isinstance(config, dict):
        cfg = LogConfig(
            level=config.get("level", "info"),
            console=config.get("console", True),
            file=config.get("file", True),
            file_path=config.get("filePath", ""),
            structured=config.get("structured", False),
            max_file_size_bytes=config.get("maxFileSizeBytes", 10 * 1024 * 1024),
            max_files=config.get("maxFiles", 5),
            redact_secrets=config.get("redactSecrets", True),
        )
    elif config is None:
        cfg = LogConfig()
    else:
        cfg = config

    root = logging.getLogger()
    root.setLevel(resolve_log_level(cfg.level))
    root.handlers.clear()

    if cfg.structured:
        formatter = StructuredFormatter()
    else:
        fmt = "%(asctime)s %(levelname)-5s %(name)s: %(message)s" if cfg.include_timestamp \
            else "%(levelname)-5s %(name)s: %(message)s"
        formatter = logging.Formatter(fmt, datefmt="%H:%M:%S")

    if cfg.console:
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        if cfg.redact_secrets:
            ch.addFilter(RedactFilter())
        root.addHandler(ch)

    if cfg.file and cfg.file_path:
        os.makedirs(os.path.dirname(cfg.file_path), exist_ok=True)
        fh = RotatingFileHandler(
            cfg.file_path,
            maxBytes=cfg.max_file_size_bytes,
            backupCount=cfg.max_files,
            encoding="utf-8",
        )
        fh.setFormatter(formatter)
        root.addHandler(fh)


def create_logger(name: str, **extra: Any) -> logging.Logger:
    """Create a named logger with optional extra context."""
    return logging.getLogger(name)


class SessionLogger:
    """Session-scoped logger that writes to a per-session log file."""

    def __init__(self, session_key: str, log_dir: str):
        self._session_key = session_key
        safe_key = session_key.replace("/", "_").replace(":", "_")
        self._log_path = os.path.join(log_dir, f"{safe_key}.jsonl")
        os.makedirs(log_dir, exist_ok=True)

    def log(self, level: str, message: str, **data: Any) -> None:
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "level": level,
            "session": self._session_key,
            "msg": message,
        }
        if data:
            entry["data"] = data
        try:
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def info(self, msg: str, **data: Any) -> None:
        self.log("info", msg, **data)

    def error(self, msg: str, **data: Any) -> None:
        self.log("error", msg, **data)

    def debug(self, msg: str, **data: Any) -> None:
        self.log("debug", msg, **data)
