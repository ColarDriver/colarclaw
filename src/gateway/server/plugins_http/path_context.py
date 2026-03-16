"""Plugin route path context — ported from openclaw server/plugins-http/path-context.ts.

Resolves and canonicalizes URL paths for plugin HTTP route matching,
including security checks for protected route prefixes.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import unquote

# Protected prefixes that always require gateway auth
PROTECTED_PLUGIN_ROUTE_PREFIXES = [
    "/api",
    "/gateway",
    "/.well-known",
]


@dataclass
class PluginRoutePathContext:
    pathname: str
    canonical_path: str
    candidates: list[str] = field(default_factory=list)
    malformed_encoding: bool = False
    decode_pass_limit_reached: bool = False
    raw_normalized_path: str = ""


def _normalize_protected_prefix(prefix: str) -> str:
    collapsed = re.sub(r"/{2,}", "/", prefix.lower())
    if len(collapsed) <= 1:
        return collapsed or "/"
    return collapsed.rstrip("/")


def prefix_match_path(pathname: str, prefix: str) -> bool:
    """Check if *pathname* matches *prefix* exactly or as a path prefix."""
    return (
        pathname == prefix
        or pathname.startswith(f"{prefix}/")
        or pathname.startswith(f"{prefix}%")
    )


_NORMALIZED_PREFIXES = [
    _normalize_protected_prefix(p) for p in PROTECTED_PLUGIN_ROUTE_PREFIXES
]


def _canonicalize_path_for_security(
    pathname: str,
    *,
    max_decode_passes: int = 3,
) -> dict:
    """Simplified port of OpenClaw's ``canonicalizePathForSecurity``."""
    raw_normalized = re.sub(r"/{2,}", "/", pathname.lower())
    candidates: list[str] = [raw_normalized]
    malformed = False
    limit_reached = False

    current = pathname
    for i in range(max_decode_passes):
        try:
            decoded = unquote(current)
        except Exception:
            malformed = True
            break
        if decoded == current:
            break
        current = decoded
        normalized = re.sub(r"/{2,}", "/", current.lower())
        if normalized not in candidates:
            candidates.append(normalized)
        if i == max_decode_passes - 1:
            limit_reached = True

    canonical = candidates[-1] if candidates else raw_normalized
    return {
        "canonicalPath": canonical,
        "candidates": candidates,
        "malformedEncoding": malformed,
        "decodePassLimitReached": limit_reached,
        "rawNormalizedPath": raw_normalized,
    }


def canonicalize_path_variant(path: str) -> str:
    """Single-pass canonicalization for comparison."""
    return re.sub(r"/{2,}", "/", path.lower()).rstrip("/") or "/"


def is_protected_plugin_route_path_from_context(
    context: PluginRoutePathContext,
) -> bool:
    """Check if any candidate path hits a protected prefix."""
    for candidate in context.candidates:
        for prefix in _NORMALIZED_PREFIXES:
            if prefix_match_path(candidate, prefix):
                return True
    if not context.malformed_encoding:
        return False
    for prefix in _NORMALIZED_PREFIXES:
        if prefix_match_path(context.raw_normalized_path, prefix):
            return True
    return False


def resolve_plugin_route_path_context(
    pathname: str,
) -> PluginRoutePathContext:
    """Port of OpenClaw's ``resolvePluginRoutePathContext``."""
    canonical = _canonicalize_path_for_security(pathname)
    return PluginRoutePathContext(
        pathname=pathname,
        canonical_path=canonical["canonicalPath"],
        candidates=canonical["candidates"],
        malformed_encoding=canonical["malformedEncoding"],
        decode_pass_limit_reached=canonical["decodePassLimitReached"],
        raw_normalized_path=canonical["rawNormalizedPath"],
    )
