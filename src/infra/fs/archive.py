"""Infra archive — ported from bk/src/infra/archive.ts, archive-path.ts.

Archive extraction (tar/zip) with security checks: path traversal prevention,
symlink traversal detection, entry count/size limits, and atomic writes.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tarfile
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

logger = logging.getLogger("infra.archive")


# ─── types ───

ArchiveKind = Literal["tar", "zip"]

TAR_SUFFIXES = [".tgz", ".tar.gz", ".tar"]


@dataclass
class ArchiveExtractLimits:
    max_archive_bytes: int = 256 * 1024 * 1024  # 256 MiB
    max_entries: int = 50_000
    max_extracted_bytes: int = 512 * 1024 * 1024  # 512 MiB
    max_entry_bytes: int = 256 * 1024 * 1024


class ArchiveSecurityError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


# ─── archive-path.ts ───

def validate_archive_entry_path(entry_path: str, escape_label: str = "archive") -> None:
    """Reject absolute paths and path traversal in archive entry paths."""
    if not entry_path:
        raise ValueError(f"{escape_label}: empty entry path")
    if os.path.isabs(entry_path):
        raise ArchiveSecurityError("path-escape", f"{escape_label}: absolute path in archive: {entry_path}")
    normalized = os.path.normpath(entry_path)
    if normalized.startswith("..") or f"{os.sep}.." in normalized:
        raise ArchiveSecurityError("path-escape", f"{escape_label}: path traversal in archive: {entry_path}")


def strip_archive_path(entry_path: str, strip: int) -> str | None:
    """Strip leading path components (like tar --strip-components)."""
    if strip <= 0:
        return entry_path
    parts = entry_path.replace("\\", "/").split("/")
    remaining = parts[strip:]
    if not remaining or all(not p for p in remaining):
        return None
    return "/".join(remaining)


def resolve_archive_output_path(
    root_dir: str, rel_path: str, original_path: str, escape_label: str = "archive",
) -> str:
    """Resolve and validate the output path for an archive entry."""
    out_path = os.path.normpath(os.path.join(root_dir, rel_path))
    root_real = os.path.realpath(root_dir)
    out_real = os.path.realpath(os.path.dirname(out_path))
    if not out_real.startswith(root_real + os.sep) and out_real != root_real:
        raise ArchiveSecurityError("path-escape", f"{escape_label}: entry escapes destination: {original_path}")
    return out_path


def resolve_archive_kind(file_path: str) -> ArchiveKind | None:
    lower = file_path.lower()
    if lower.endswith(".zip"):
        return "zip"
    if any(lower.endswith(s) for s in TAR_SUFFIXES):
        return "tar"
    return None


# ─── byte budget tracking ───

class _ByteBudgetTracker:
    def __init__(self, limits: ArchiveExtractLimits):
        self.limits = limits
        self.entry_bytes = 0
        self.extracted_bytes = 0

    def start_entry(self) -> None:
        self.entry_bytes = 0

    def add_bytes(self, n: int) -> None:
        n = max(0, n)
        if n == 0:
            return
        self.entry_bytes += n
        if self.entry_bytes > self.limits.max_entry_bytes:
            raise ValueError("archive entry extracted size exceeds limit")
        self.extracted_bytes += n
        if self.extracted_bytes > self.limits.max_extracted_bytes:
            raise ValueError("archive extracted size exceeds limit")

    def add_entry_size(self, size: int) -> None:
        s = max(0, size)
        if s > self.limits.max_entry_bytes:
            raise ValueError("archive entry extracted size exceeds limit")
        self.add_bytes(s)


# ─── resolve packed root dir ───

async def resolve_packed_root_dir(extract_dir: str) -> str:
    """Resolve the root directory of an extracted npm package archive."""
    direct = os.path.join(extract_dir, "package")
    if os.path.isdir(direct):
        return direct
    entries = [e for e in os.listdir(extract_dir) if os.path.isdir(os.path.join(extract_dir, e))]
    if len(entries) != 1:
        raise ValueError(f"unexpected archive layout (dirs: {', '.join(entries)})")
    return os.path.join(extract_dir, entries[0])


# ─── symlink traversal checks ───

def _assert_no_symlink_traversal(root_dir: str, rel_path: str, original_path: str) -> None:
    """Check that no intermediate path component is a symlink."""
    parts = rel_path.replace("\\", "/").split("/")
    current = os.path.abspath(root_dir)
    for part in parts:
        if not part:
            continue
        current = os.path.join(current, part)
        if os.path.islink(current):
            raise ArchiveSecurityError(
                "destination-symlink-traversal",
                f"archive entry traverses symlink in destination: {original_path}",
            )


def _assert_destination_dir_ready(dest_dir: str) -> str:
    """Assert that dest_dir is a real directory, not a symlink."""
    if os.path.islink(dest_dir):
        raise ArchiveSecurityError("destination-symlink", "archive destination is a symlink")
    if not os.path.isdir(dest_dir):
        raise ArchiveSecurityError("destination-not-directory", "archive destination is not a directory")
    return os.path.realpath(dest_dir)


# ─── tar extraction ───

BLOCKED_TAR_TYPES = {"symlink", "link", "blk", "chr", "fifo"}


def _safe_tar_extract(
    archive_path: str,
    dest_dir: str,
    strip: int = 0,
    limits: ArchiveExtractLimits | None = None,
) -> None:
    """Extract a tar archive with security checks."""
    lim = limits or ArchiveExtractLimits()
    dest_real = _assert_destination_dir_ready(dest_dir)

    file_size = os.path.getsize(archive_path)
    if file_size > lim.max_archive_bytes:
        raise ValueError("archive size exceeds limit")

    budget = _ByteBudgetTracker(lim)
    entry_count = 0

    with tarfile.open(archive_path, "r:*") as tf:
        for member in tf:
            entry_count += 1
            if entry_count > lim.max_entries:
                raise ValueError("archive entry count exceeds limit")

            # Security: reject symlinks and special files
            if member.issym() or member.islnk():
                raise ArchiveSecurityError("path-escape", f"tar entry is a link: {member.name}")
            if not member.isfile() and not member.isdir():
                continue

            # Strip components
            rel_path = strip_archive_path(member.name, strip)
            if not rel_path:
                continue

            validate_archive_entry_path(rel_path)
            out_path = resolve_archive_output_path(dest_real, rel_path, member.name)
            _assert_no_symlink_traversal(dest_dir, rel_path, member.name)

            if member.isdir():
                os.makedirs(out_path, exist_ok=True)
                continue

            # File extraction with budget tracking
            budget.start_entry()
            budget.add_entry_size(member.size)

            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with tf.extractfile(member) as src:
                if src is None:
                    continue
                with open(out_path, "wb") as dst:
                    while True:
                        chunk = src.read(65536)
                        if not chunk:
                            break
                        dst.write(chunk)

            # Restore permissions (file only, no setuid/setgid)
            if member.mode:
                mode = member.mode & 0o777
                if mode:
                    os.chmod(out_path, mode)


# ─── zip extraction ───

def _safe_zip_extract(
    archive_path: str,
    dest_dir: str,
    strip: int = 0,
    limits: ArchiveExtractLimits | None = None,
) -> None:
    """Extract a zip archive with security checks."""
    lim = limits or ArchiveExtractLimits()
    dest_real = _assert_destination_dir_ready(dest_dir)

    file_size = os.path.getsize(archive_path)
    if file_size > lim.max_archive_bytes:
        raise ValueError("archive size exceeds limit")

    budget = _ByteBudgetTracker(lim)

    with zipfile.ZipFile(archive_path, "r") as zf:
        entries = zf.infolist()
        if len(entries) > lim.max_entries:
            raise ValueError("archive entry count exceeds limit")

        for entry in entries:
            rel_path = strip_archive_path(entry.filename, strip)
            if not rel_path:
                continue

            validate_archive_entry_path(rel_path)
            out_path = resolve_archive_output_path(dest_real, rel_path, entry.filename)
            _assert_no_symlink_traversal(dest_dir, rel_path, entry.filename)

            if entry.is_dir():
                os.makedirs(out_path, exist_ok=True)
                continue

            # File extraction with budget
            budget.start_entry()
            budget.add_entry_size(entry.file_size)

            os.makedirs(os.path.dirname(out_path), exist_ok=True)

            # Atomic write via temp file
            temp_path = os.path.join(
                os.path.dirname(out_path),
                f".{os.path.basename(out_path)}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp",
            )
            try:
                with zf.open(entry) as src, open(temp_path, "wb") as dst:
                    while True:
                        chunk = src.read(65536)
                        if not chunk:
                            break
                        dst.write(chunk)
                os.replace(temp_path, out_path)
            except Exception:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
                raise

            # Restore unix permissions from zip external attrs
            if entry.external_attr:
                unix_mode = (entry.external_attr >> 16) & 0o777
                if unix_mode:
                    os.chmod(out_path, unix_mode)


# ─── public API ───

async def extract_archive(
    archive_path: str,
    dest_dir: str,
    timeout_ms: int = 60_000,
    kind: ArchiveKind | None = None,
    strip_components: int = 0,
    limits: ArchiveExtractLimits | None = None,
) -> None:
    """Extract an archive (tar or zip) with security and resource limits."""
    resolved_kind = kind or resolve_archive_kind(archive_path)
    if not resolved_kind:
        raise ValueError(f"unsupported archive: {archive_path}")

    strip = max(0, strip_components)

    loop = asyncio.get_event_loop()
    if resolved_kind == "tar":
        await asyncio.wait_for(
            loop.run_in_executor(None, _safe_tar_extract, archive_path, dest_dir, strip, limits),
            timeout=timeout_ms / 1000.0,
        )
    else:
        await asyncio.wait_for(
            loop.run_in_executor(None, _safe_zip_extract, archive_path, dest_dir, strip, limits),
            timeout=timeout_ms / 1000.0,
        )


# ─── utilities ───

async def file_exists(file_path: str) -> bool:
    return os.path.exists(file_path)


def read_json_file(file_path: str) -> Any:
    import json
    with open(file_path, "r") as f:
        return json.load(f)
