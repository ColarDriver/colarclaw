"""Infra file operations — ported from bk/src/infra/file-lock.ts, fs-safe.ts,
file-identity.ts, hardlink-guards.ts, boundary-file-read.ts, boundary-path.ts,
archive.ts, archive-path.ts, json-stream.ts, json-write.ts, locked-json-store.ts,
map-size.ts, stream-lines.ts, temp-file.ts, watch-file.ts.

File locking, safe FS ops, identity, archives, JSON stores, streaming, temp files.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import stat
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


# ─── file-lock.ts ───

@dataclass
class FileLockHandle:
    path: str = ""
    fd: int | None = None

    def release(self) -> None:
        if self.fd is not None:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_UN)
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.release()


def acquire_file_lock(path: str, timeout_ms: int = 10000) -> FileLockHandle:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR)
    deadline = time.time() + timeout_ms / 1000.0
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return FileLockHandle(path=path, fd=fd)
        except (OSError, BlockingIOError):
            if time.time() >= deadline:
                os.close(fd)
                raise TimeoutError(f"file lock timeout: {path}")
            time.sleep(0.01)


def with_file_lock(path: str, fn: Callable[..., Any], timeout_ms: int = 10000) -> Any:
    lock = acquire_file_lock(path, timeout_ms)
    try:
        return fn()
    finally:
        lock.release()


# ─── fs-safe.ts ───

def safe_read_file(path: str, encoding: str = "utf-8") -> str | None:
    try:
        with open(path, "r", encoding=encoding) as f:
            return f.read()
    except (OSError, UnicodeDecodeError):
        return None


def safe_read_bytes(path: str) -> bytes | None:
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError:
        return None


def safe_write_file(path: str, content: str, encoding: str = "utf-8") -> bool:
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding=encoding) as f:
            f.write(content)
        return True
    except OSError:
        return False


def safe_unlink(path: str) -> bool:
    try:
        os.unlink(path)
        return True
    except OSError:
        return False


def safe_mkdir(path: str, parents: bool = True) -> bool:
    try:
        os.makedirs(path, exist_ok=parents)
        return True
    except OSError:
        return False


def safe_stat(path: str) -> os.stat_result | None:
    try:
        return os.stat(path)
    except OSError:
        return None


def safe_lstat(path: str) -> os.stat_result | None:
    try:
        return os.lstat(path)
    except OSError:
        return None


def safe_rename(src: str, dst: str) -> bool:
    try:
        os.replace(src, dst)
        return True
    except OSError:
        return False


# ─── file-identity.ts ───

def compute_file_sha256(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def compute_bytes_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ─── hardlink-guards.ts ───

def is_hardlink(path: str) -> bool:
    st = safe_lstat(path)
    if not st:
        return False
    return st.st_nlink > 1 if stat.S_ISREG(st.st_mode) else False


def is_symlink(path: str) -> bool:
    return os.path.islink(path)


# ─── boundary-file-read.ts / boundary-path.ts ───

def read_boundary_file(path: str, max_bytes: int = 1024 * 1024) -> str | None:
    st = safe_stat(path)
    if not st or st.st_size > max_bytes:
        return None
    return safe_read_file(path)


def is_path_within_boundary(path: str, boundary: str) -> bool:
    abs_path = os.path.abspath(path)
    abs_boundary = os.path.abspath(boundary)
    return abs_path.startswith(abs_boundary + os.sep) or abs_path == abs_boundary


# ─── archive.ts / archive-path.ts ───

def create_tar_archive(source_dir: str, output_path: str, compression: str = "gz") -> bool:
    try:
        import tarfile
        mode = f"w:{compression}" if compression else "w"
        with tarfile.open(output_path, mode) as tar:
            tar.add(source_dir, arcname=os.path.basename(source_dir))
        return True
    except Exception:
        return False


def extract_tar_archive(archive_path: str, target_dir: str) -> bool:
    try:
        import tarfile
        with tarfile.open(archive_path) as tar:
            tar.extractall(path=target_dir, filter="data")
        return True
    except Exception:
        return False


def resolve_archive_path(base_dir: str, name: str, ext: str = ".tar.gz") -> str:
    return os.path.join(base_dir, f"{name}{ext}")


# ─── json-write.ts / json-stream.ts ───

def write_json_file_atomically(path: str, data: Any, indent: int = 2) -> None:
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json_file_safe(path: str, fallback: Any = None) -> Any:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return fallback


# ─── locked-json-store.ts ───

class LockedJsonStore:
    def __init__(self, path: str, lock_path: str | None = None):
        self.path = path
        self.lock_path = lock_path or f"{path}.lock"

    def read(self, fallback: Any = None) -> Any:
        return read_json_file_safe(self.path, fallback)

    def write(self, data: Any) -> None:
        lock = acquire_file_lock(self.lock_path)
        try:
            write_json_file_atomically(self.path, data)
        finally:
            lock.release()

    def update(self, fn: Callable[[Any], Any], fallback: Any = None) -> Any:
        lock = acquire_file_lock(self.lock_path)
        try:
            current = read_json_file_safe(self.path, fallback)
            updated = fn(current)
            write_json_file_atomically(self.path, updated)
            return updated
        finally:
            lock.release()


# ─── map-size.ts ───

def prune_dict_to_max_size(d: dict[str, Any], max_size: int) -> None:
    while len(d) > max_size:
        oldest_key = next(iter(d))
        del d[oldest_key]


# ─── stream-lines.ts ───

def stream_file_lines(path: str, callback: Callable[[str], None], encoding: str = "utf-8") -> int:
    count = 0
    try:
        with open(path, "r", encoding=encoding) as f:
            for line in f:
                callback(line.rstrip("\n"))
                count += 1
    except OSError:
        pass
    return count


# ─── temp-file.ts ───

def create_temp_file(suffix: str = "", prefix: str = "openclaw-", dir: str | None = None) -> str:
    fd, path = tempfile.mkstemp(suffix=suffix, prefix=prefix, dir=dir)
    os.close(fd)
    return path


def create_temp_dir(prefix: str = "openclaw-", dir: str | None = None) -> str:
    return tempfile.mkdtemp(prefix=prefix, dir=dir)


# ─── watch-file.ts ───

def watch_file_mtime(path: str) -> float | None:
    st = safe_stat(path)
    return st.st_mtime if st else None


# ─── fs-safe.ts: safe file operations with boundary checking ───

import asyncio
import logging

logger = logging.getLogger("infra.file_ops")


class SafeOpenError(Exception):
    """Error for safe file operations with typed error codes."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code  # "invalid-path" | "not-found" | "outside-workspace" | "symlink" | "not-file" | "path-mismatch" | "too-large"


def _is_path_inside(root: str, target: str) -> bool:
    """Check if target path is inside root (using real/absolute paths)."""
    root_abs = os.path.abspath(root)
    target_abs = os.path.abspath(target)
    if not root_abs.endswith(os.sep):
        root_abs += os.sep
    return target_abs.startswith(root_abs) or target_abs == root_abs.rstrip(os.sep)


def _verify_local_file(file_path: str, reject_hardlinks: bool = False) -> tuple[str, os.stat_result]:
    """Verify a local file is safe to access (not symlink, not hardlinked)."""
    try:
        lst = os.lstat(file_path)
    except FileNotFoundError:
        raise SafeOpenError("not-found", "file not found")
    except OSError:
        raise SafeOpenError("invalid-path", f"cannot access: {file_path}")

    if stat.S_ISDIR(lst.st_mode):
        raise SafeOpenError("not-file", "not a file")
    if stat.S_ISLNK(lst.st_mode):
        raise SafeOpenError("symlink", "symlink not allowed")
    if not stat.S_ISREG(lst.st_mode):
        raise SafeOpenError("not-file", "not a regular file")
    if reject_hardlinks and lst.st_nlink > 1:
        raise SafeOpenError("invalid-path", "hardlinked path not allowed")

    try:
        real_path = os.path.realpath(file_path)
    except OSError:
        raise SafeOpenError("path-mismatch", "unable to resolve file path")

    try:
        real_stat = os.stat(real_path)
    except FileNotFoundError:
        raise SafeOpenError("not-found", "file not found")

    if lst.st_ino != real_stat.st_ino or lst.st_dev != real_stat.st_dev:
        raise SafeOpenError("path-mismatch", "path changed during read")
    if reject_hardlinks and real_stat.st_nlink > 1:
        raise SafeOpenError("invalid-path", "hardlinked path not allowed")

    return real_path, real_stat


def read_file_within_root(
    root_dir: str,
    relative_path: str,
    max_bytes: int | None = None,
    reject_hardlinks: bool = True,
) -> tuple[bytes, str]:
    """Safely read a file within a root directory boundary.

    Returns (file_contents, real_path).
    Raises SafeOpenError on boundary violations, symlinks, etc.
    """
    root_real = os.path.realpath(root_dir)
    resolved = os.path.normpath(os.path.join(root_real, relative_path))
    if not _is_path_inside(root_real, resolved):
        raise SafeOpenError("outside-workspace", "file is outside workspace root")

    real_path, file_stat = _verify_local_file(resolved, reject_hardlinks)
    if not _is_path_inside(root_real, real_path):
        raise SafeOpenError("outside-workspace", "file is outside workspace root")

    if max_bytes is not None and file_stat.st_size > max_bytes:
        raise SafeOpenError("too-large", f"file exceeds limit of {max_bytes} bytes (got {file_stat.st_size})")

    data = safe_read_bytes(real_path)
    if data is None:
        raise SafeOpenError("not-found", "unable to read file")
    return data, real_path


def write_file_within_root(
    root_dir: str,
    relative_path: str,
    data: str | bytes,
    encoding: str = "utf-8",
    mkdir: bool = True,
) -> None:
    """Safely write a file within a root directory boundary with atomic replacement."""
    root_real = os.path.realpath(root_dir)
    resolved = os.path.normpath(os.path.join(root_real, relative_path))
    if not _is_path_inside(root_real, resolved):
        raise SafeOpenError("outside-workspace", "file is outside workspace root")

    # Check for symlink at target
    if os.path.islink(resolved):
        raise SafeOpenError("symlink", "symlink target not allowed for write")

    parent_dir = os.path.dirname(resolved)
    if mkdir:
        os.makedirs(parent_dir, exist_ok=True)

    # Atomic write via temp file
    fd, tmp_path = tempfile.mkstemp(dir=parent_dir, prefix=f".{os.path.basename(resolved)}.", suffix=".tmp")
    try:
        if isinstance(data, str):
            with os.fdopen(fd, "w", encoding=encoding) as f:
                f.write(data)
        else:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
        os.replace(tmp_path, resolved)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise

    # Post-write boundary verification
    real_after = os.path.realpath(resolved)
    if not _is_path_inside(root_real, real_after):
        logger.warning("post-write verification failed: file outside workspace root")
        try:
            os.unlink(resolved)
        except OSError:
            pass
        raise SafeOpenError("outside-workspace", "file landed outside workspace root after write")


def copy_file_within_root(
    source_path: str,
    root_dir: str,
    relative_path: str,
    max_bytes: int | None = None,
    mkdir: bool = True,
    reject_source_hardlinks: bool = True,
) -> None:
    """Safely copy a file into a root directory boundary."""
    real_source, source_stat = _verify_local_file(source_path, reject_source_hardlinks)
    if max_bytes is not None and source_stat.st_size > max_bytes:
        raise SafeOpenError("too-large", f"file exceeds limit of {max_bytes} bytes (got {source_stat.st_size})")

    data = safe_read_bytes(real_source)
    if data is None:
        raise SafeOpenError("not-found", "unable to read source file")

    write_file_within_root(root_dir, relative_path, data, mkdir=mkdir)


def read_local_file_safely(file_path: str, max_bytes: int | None = None) -> tuple[bytes, str]:
    """Safely read a local file (no root boundary, but validates symlinks/hardlinks)."""
    real_path, file_stat = _verify_local_file(file_path)
    if max_bytes is not None and file_stat.st_size > max_bytes:
        raise SafeOpenError("too-large", f"file exceeds limit of {max_bytes} bytes (got {file_stat.st_size})")

    data = safe_read_bytes(real_path)
    if data is None:
        raise SafeOpenError("not-found", "unable to read file")
    return data, real_path


def create_root_scoped_read_file(
    root_dir: str,
    max_bytes: int | None = None,
    reject_hardlinks: bool = True,
) -> Callable[[str], bytes]:
    """Create a factory function for reading files scoped to a root directory."""
    root_abs = os.path.abspath(root_dir)

    def reader(file_path: str) -> bytes:
        if os.path.isabs(file_path):
            relative = os.path.relpath(file_path, root_abs)
        else:
            relative = file_path
        data, _real = read_file_within_root(
            root_abs, relative, max_bytes=max_bytes, reject_hardlinks=reject_hardlinks)
        return data

    return reader


# ─── jsonl-stream.ts ───

def read_jsonl_records(file_path: str) -> list[dict[str, Any]]:
    """Read all valid JSON records from a JSONL file."""
    records: list[dict[str, Any]] = []
    try:
        with open(file_path, "r") as f:
            for line in f:
                trimmed = line.strip()
                if not trimmed:
                    continue
                try:
                    parsed = __import__("json").loads(trimmed)
                    if isinstance(parsed, dict):
                        records.append(parsed)
                except ValueError:
                    continue
    except OSError:
        pass
    return records


def append_jsonl_record(file_path: str, record: dict[str, Any]) -> bool:
    """Append a JSON record to a JSONL file."""
    try:
        parent = os.path.dirname(file_path) or "."
        os.makedirs(parent, exist_ok=True)
        with open(file_path, "a") as f:
            f.write(__import__("json").dumps(record, ensure_ascii=False) + "\n")
        return True
    except OSError:
        return False


# ─── safe-copy.ts ───

def safe_copy_file(src: str, dst: str, overwrite: bool = False) -> bool:
    """Safely copy a file with optional overwrite."""
    try:
        if not os.path.isfile(src):
            return False
        if not overwrite and os.path.exists(dst):
            return False
        parent = os.path.dirname(dst) or "."
        os.makedirs(parent, exist_ok=True)
        shutil.copy2(src, dst)
        return True
    except OSError:
        return False


def safe_copy_dir(src: str, dst: str) -> bool:
    """Safely copy a directory tree."""
    try:
        if not os.path.isdir(src):
            return False
        shutil.copytree(src, dst, dirs_exist_ok=True)
        return True
    except OSError:
        return False


# ─── atomic-json.ts ───

def write_json_file_with_backup(
    path_str: str,
    data: Any,
    indent: int = 2,
    backup_suffix: str = ".bak",
) -> None:
    """Write JSON file atomically with optional backup of existing file."""
    if os.path.isfile(path_str) and backup_suffix:
        backup_path = path_str + backup_suffix
        try:
            shutil.copy2(path_str, backup_path)
        except OSError:
            pass
    write_json_file_atomically(path_str, data, indent)
