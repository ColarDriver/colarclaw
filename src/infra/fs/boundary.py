"""Infra boundary — ported from bk/src/infra/boundary-path.ts,
boundary-file-read.ts, safe-open-sync.ts, hardlink-guards.ts,
path-alias-guards.ts, path-guards.ts, path-safety.ts.

Boundary path resolution, safe file open, hardlink guards,
path traversal validation, symlink escape detection.
"""
from __future__ import annotations

import asyncio
import errno
import logging
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("infra.boundary")


# ─── path-guards.ts ───

def is_not_found_error(error: Exception) -> bool:
    """Check if error is a file-not-found error."""
    if isinstance(error, (FileNotFoundError, NotADirectoryError)):
        return True
    if isinstance(error, OSError):
        return error.errno in (errno.ENOENT, errno.ENOTDIR)
    return False


def is_path_inside(root: str, candidate: str) -> bool:
    """Check if candidate is inside root (canonically)."""
    root_abs = os.path.abspath(root)
    candidate_abs = os.path.abspath(candidate)
    if candidate_abs == root_abs:
        return True
    return candidate_abs.startswith(root_abs + os.sep)


def guard_path_traversal(root: str, target: str, label: str = "path") -> None:
    """Raise if target escapes root."""
    if not is_path_inside(root, target):
        raise ValueError(
            f"Path escapes {label} ({_short_path(root)}): {_short_path(target)}"
        )


def _short_path(value: str) -> str:
    home = str(Path.home())
    if value.startswith(home):
        return "~" + value[len(home):]
    return value


# ─── path-safety.ts ───

def is_safe_path(path_str: str) -> bool:
    """Check if a path is safe (no traversal/special chars)."""
    if not path_str:
        return False
    if "\x00" in path_str:
        return False
    parts = Path(path_str).parts
    for part in parts:
        if part == "..":
            return False
    return True


# ─── path-alias-guards.ts ───

def has_path_alias(path_str: str) -> bool:
    """Check if a path contains symlinks (aliases)."""
    try:
        real = os.path.realpath(path_str)
        return os.path.abspath(path_str) != real
    except OSError:
        return False


async def has_path_alias_async(path_str: str) -> bool:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, has_path_alias, path_str)


# ─── safe-open-sync.ts ───

SafeOpenFailureReason = Literal["path", "validation", "io"]


@dataclass
class SafeOpenResult:
    ok: bool = False
    path: str = ""
    fd: int = -1
    stat_result: os.stat_result | None = None
    reason: str | None = None  # SafeOpenFailureReason
    error: Exception | None = None


def same_file_identity(a: os.stat_result, b: os.stat_result) -> bool:
    """Check if two stat results refer to the same file (dev+ino)."""
    return a.st_dev == b.st_dev and a.st_ino == b.st_ino


def open_verified_file(
    file_path: str,
    resolved_path: str | None = None,
    reject_symlink: bool = False,
    reject_hardlinks: bool = True,
    max_bytes: int | None = None,
    allowed_type: str = "file",
) -> SafeOpenResult:
    """Open a file after verifying it's safe (no symlinks, hardlinks, size ok)."""
    fd = None
    try:
        if reject_symlink:
            cstat = os.lstat(file_path)
            if stat.S_ISLNK(cstat.st_mode):
                return SafeOpenResult(reason="validation")

        real_path = resolved_path or os.path.realpath(file_path)
        pre_stat = os.lstat(real_path)

        if allowed_type == "file" and not stat.S_ISREG(pre_stat.st_mode):
            return SafeOpenResult(reason="validation")
        if allowed_type == "directory" and not stat.S_ISDIR(pre_stat.st_mode):
            return SafeOpenResult(reason="validation")

        if reject_hardlinks and stat.S_ISREG(pre_stat.st_mode) and pre_stat.st_nlink > 1:
            return SafeOpenResult(reason="validation")

        if max_bytes is not None and stat.S_ISREG(pre_stat.st_mode) and pre_stat.st_size > max_bytes:
            return SafeOpenResult(reason="validation")

        # O_NOFOLLOW may not be available on all platforms
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW

        fd = os.open(real_path, flags)
        opened_stat = os.fstat(fd)

        if allowed_type == "file" and not stat.S_ISREG(opened_stat.st_mode):
            return SafeOpenResult(reason="validation")
        if reject_hardlinks and stat.S_ISREG(opened_stat.st_mode) and opened_stat.st_nlink > 1:
            return SafeOpenResult(reason="validation")
        if max_bytes is not None and stat.S_ISREG(opened_stat.st_mode) and opened_stat.st_size > max_bytes:
            return SafeOpenResult(reason="validation")

        if not same_file_identity(pre_stat, opened_stat):
            return SafeOpenResult(reason="validation")

        result = SafeOpenResult(ok=True, path=real_path, fd=fd, stat_result=opened_stat)
        fd = None  # Transferred ownership
        return result

    except FileNotFoundError as e:
        return SafeOpenResult(reason="path", error=e)
    except OSError as e:
        if e.errno in (errno.ENOENT, errno.ENOTDIR, errno.ELOOP):
            return SafeOpenResult(reason="path", error=e)
        return SafeOpenResult(reason="io", error=e)
    finally:
        if fd is not None:
            os.close(fd)


# ─── hardlink-guards.ts ───

async def assert_no_hardlinked_final_path(
    file_path: str,
    root: str,
    boundary_label: str,
    allow_final_hardlink_for_unlink: bool = False,
) -> None:
    """Assert a file isn't hardlinked (TOCTOU-safe)."""
    if allow_final_hardlink_for_unlink:
        return
    try:
        st = os.stat(file_path)
    except FileNotFoundError:
        return
    if not stat.S_ISREG(st.st_mode):
        return
    if st.st_nlink > 1:
        raise ValueError(
            f"Hardlinked path is not allowed under {boundary_label} "
            f"({_short_path(root)}): {_short_path(file_path)}"
        )


# ─── boundary-path.ts ───

BoundaryPathKind = Literal["missing", "file", "directory", "symlink", "other"]


@dataclass
class ResolvedBoundaryPath:
    absolute_path: str = ""
    canonical_path: str = ""
    root_path: str = ""
    root_canonical_path: str = ""
    relative_path: str = ""
    exists: bool = False
    kind: str = "missing"  # BoundaryPathKind


def _get_path_kind(absolute_path: str, preserve_final_symlink: bool = False) -> tuple[bool, str]:
    """Get the kind of a path."""
    try:
        if preserve_final_symlink:
            st = os.lstat(absolute_path)
        else:
            st = os.stat(absolute_path)
        if stat.S_ISREG(st.st_mode):
            return True, "file"
        if stat.S_ISDIR(st.st_mode):
            return True, "directory"
        if stat.S_ISLNK(st.st_mode):
            return True, "symlink"
        return True, "other"
    except FileNotFoundError:
        return False, "missing"
    except OSError:
        return False, "missing"


def _resolve_via_existing_ancestor(target_path: str) -> str:
    """Resolve path via nearest existing ancestor."""
    normalized = os.path.abspath(target_path)
    cursor = normalized
    missing_suffix: list[str] = []

    while cursor != os.path.dirname(cursor) and not os.path.exists(cursor):
        missing_suffix.insert(0, os.path.basename(cursor))
        cursor = os.path.dirname(cursor)

    if not os.path.exists(cursor):
        return normalized

    try:
        resolved = os.path.realpath(cursor)
        if not missing_suffix:
            return resolved
        return os.path.join(resolved, *missing_suffix)
    except OSError:
        return normalized


def _relative_inside_root(root_path: str, target_path: str) -> str:
    rel = os.path.relpath(os.path.abspath(target_path), os.path.abspath(root_path))
    if not rel or rel == ".":
        return ""
    if rel.startswith("..") or os.path.isabs(rel):
        return ""
    return rel


def resolve_boundary_path(
    absolute_path: str,
    root_path: str,
    boundary_label: str,
    root_canonical_path: str | None = None,
    skip_lexical_root_check: bool = False,
) -> ResolvedBoundaryPath:
    """Resolve a path within a boundary, following symlinks and checking escapes."""
    root_abs = os.path.abspath(root_path)
    abs_path = os.path.abspath(absolute_path)
    root_canon = root_canonical_path or _resolve_via_existing_ancestor(root_abs)
    root_canon = os.path.abspath(root_canon)

    lexical_inside = is_path_inside(root_abs, abs_path)

    if not skip_lexical_root_check and not lexical_inside:
        # Check if canonically inside
        canonical_outside = _resolve_via_existing_ancestor(abs_path)
        if not is_path_inside(root_canon, canonical_outside):
            raise ValueError(
                f"Path escapes {boundary_label} ({_short_path(root_abs)}): {_short_path(abs_path)}"
            )
        # Path is outside lexically but canonically inside
        exists, kind = _get_path_kind(abs_path)
        return ResolvedBoundaryPath(
            absolute_path=abs_path,
            canonical_path=canonical_outside,
            root_path=root_abs,
            root_canonical_path=root_canon,
            relative_path=_relative_inside_root(root_canon, canonical_outside),
            exists=exists,
            kind=kind,
        )

    # Walk segments lexically, resolving symlinks
    rel = os.path.relpath(abs_path, root_abs)
    segments = [s for s in rel.split(os.sep) if s]
    canonical_cursor = root_canon
    lexical_cursor = root_abs

    for i, segment in enumerate(segments):
        lexical_cursor = os.path.join(lexical_cursor, segment)
        try:
            lstat = os.lstat(lexical_cursor)
        except FileNotFoundError:
            # Missing — append remaining segments
            remaining = segments[i:]
            canonical_cursor = os.path.join(canonical_cursor, *remaining)
            if not is_path_inside(root_canon, canonical_cursor):
                raise ValueError(
                    f"Path resolves outside {boundary_label} ({_short_path(root_canon)}): {_short_path(abs_path)}"
                )
            break
        except OSError:
            canonical_cursor = os.path.join(canonical_cursor, segment)
            break

        if stat.S_ISLNK(lstat.st_mode):
            # Follow symlink and check it stays inside
            link_canonical = os.path.realpath(lexical_cursor)
            if not is_path_inside(root_canon, link_canonical):
                raise ValueError(
                    f"Symlink escapes {boundary_label} ({_short_path(root_canon)}): {_short_path(lexical_cursor)}"
                )
            canonical_cursor = link_canonical
            lexical_cursor = link_canonical
        else:
            canonical_cursor = os.path.join(canonical_cursor, segment)
            if not is_path_inside(root_canon, canonical_cursor):
                raise ValueError(
                    f"Path resolves outside {boundary_label} ({_short_path(root_canon)}): {_short_path(abs_path)}"
                )

    exists, kind = _get_path_kind(abs_path)
    return ResolvedBoundaryPath(
        absolute_path=abs_path,
        canonical_path=canonical_cursor,
        root_path=root_abs,
        root_canonical_path=root_canon,
        relative_path=_relative_inside_root(root_canon, canonical_cursor),
        exists=exists,
        kind=kind,
    )


# ─── boundary-file-read.ts ───

@dataclass
class BoundaryFileOpenResult:
    ok: bool = False
    path: str = ""
    fd: int = -1
    stat_result: os.stat_result | None = None
    root_real_path: str = ""
    reason: str | None = None
    error: Exception | None = None


def open_boundary_file(
    absolute_path: str,
    root_path: str,
    boundary_label: str,
    root_real_path: str | None = None,
    max_bytes: int | None = None,
    reject_hardlinks: bool = True,
    allowed_type: str = "file",
    skip_lexical_root_check: bool = False,
) -> BoundaryFileOpenResult:
    """Open a file within a boundary with full security checks."""
    try:
        resolved = resolve_boundary_path(
            absolute_path=absolute_path,
            root_path=root_path,
            boundary_label=boundary_label,
            root_canonical_path=root_real_path,
            skip_lexical_root_check=skip_lexical_root_check,
        )
    except ValueError as e:
        return BoundaryFileOpenResult(reason="validation", error=e)

    opened = open_verified_file(
        file_path=absolute_path,
        resolved_path=resolved.canonical_path,
        reject_hardlinks=reject_hardlinks,
        max_bytes=max_bytes,
        allowed_type=allowed_type,
    )
    if not opened.ok:
        return BoundaryFileOpenResult(
            reason=opened.reason,
            error=opened.error,
        )

    return BoundaryFileOpenResult(
        ok=True,
        path=opened.path,
        fd=opened.fd,
        stat_result=opened.stat_result,
        root_real_path=resolved.root_canonical_path,
    )
