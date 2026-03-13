"""ACP session mapper — ported from bk/src/acp/session-mapper.ts.

Session key resolution, meta parsing, and session reset.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .meta import read_bool, read_string
from .types import AcpServerOptions


@dataclass
class AcpSessionMeta:
    session_key: str | None = None
    session_label: str | None = None
    reset_session: bool | None = None
    require_existing: bool | None = None
    prefix_cwd: bool | None = None


def parse_session_meta(meta: Any) -> AcpSessionMeta:
    if not meta or not isinstance(meta, dict):
        return AcpSessionMeta()
    return AcpSessionMeta(
        session_key=read_string(meta, ["sessionKey", "session", "key"]),
        session_label=read_string(meta, ["sessionLabel", "label"]),
        reset_session=read_bool(meta, ["resetSession", "reset"]),
        require_existing=read_bool(meta, ["requireExistingSession", "requireExisting"]),
        prefix_cwd=read_bool(meta, ["prefixCwd"]),
    )


async def resolve_session_key(
    meta: AcpSessionMeta,
    fallback_key: str,
    gateway: Any = None,
    opts: AcpServerOptions | None = None,
) -> str:
    requested_label = meta.session_label or (opts.default_session_label if opts else None)
    requested_key = meta.session_key or (opts.default_session_key if opts else None)
    require_existing = meta.require_existing if meta.require_existing is not None else (
        opts.require_existing_session if opts else False
    )

    if meta.session_label and gateway:
        resolved = await gateway.request("sessions.resolve", {"label": meta.session_label})
        if not resolved or not resolved.get("key"):
            raise ValueError(f"Unable to resolve session label: {meta.session_label}")
        return resolved["key"]

    if meta.session_key:
        if not require_existing:
            return meta.session_key
        if gateway:
            resolved = await gateway.request("sessions.resolve", {"key": meta.session_key})
            if not resolved or not resolved.get("key"):
                raise ValueError(f"Session key not found: {meta.session_key}")
            return resolved["key"]
        return meta.session_key

    if requested_label and gateway:
        resolved = await gateway.request("sessions.resolve", {"label": requested_label})
        if not resolved or not resolved.get("key"):
            raise ValueError(f"Unable to resolve session label: {requested_label}")
        return resolved["key"]

    if requested_key:
        if not require_existing:
            return requested_key
        if gateway:
            resolved = await gateway.request("sessions.resolve", {"key": requested_key})
            if not resolved or not resolved.get("key"):
                raise ValueError(f"Session key not found: {requested_key}")
            return resolved["key"]
        return requested_key

    return fallback_key


async def reset_session_if_needed(
    meta: AcpSessionMeta,
    session_key: str,
    gateway: Any = None,
    opts: AcpServerOptions | None = None,
) -> None:
    should_reset = meta.reset_session if meta.reset_session is not None else (
        opts.reset_session if opts else False
    )
    if not should_reset:
        return
    if gateway:
        await gateway.request("sessions.reset", {"key": session_key})
