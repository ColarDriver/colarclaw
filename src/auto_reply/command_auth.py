"""Auto-reply command auth — ported from bk/src/auto-reply/command-auth.ts."""
from __future__ import annotations

from typing import Any

from .types import CommandAuthorization


def resolve_command_authorization(
    ctx: Any,
    cfg: Any,
    command_authorized: bool,
) -> CommandAuthorization:
    from_ = (getattr(ctx, "From", "") or "").strip()
    to = (getattr(ctx, "To", "") or "").strip()
    sender_id = (getattr(ctx, "SenderId", "") or "").strip() or None
    sender_e164 = (getattr(ctx, "SenderE164", "") or "").strip() or None

    allow_from_raw: list[str] = []
    owner_allow_from: list[str] = []

    commands_cfg = getattr(cfg, "commands", None)
    if commands_cfg:
        raw_owners = getattr(commands_cfg, "owner_allow_from", None) or getattr(commands_cfg, "ownerAllowFrom", None)
        if isinstance(raw_owners, list):
            owner_allow_from = [str(e).strip() for e in raw_owners if str(e).strip()]

    allow_all = len(allow_from_raw) == 0 or any(e.strip() == "*" for e in allow_from_raw)
    owner_all = any(e.strip() == "*" for e in owner_allow_from)
    explicit_owners = [e for e in owner_allow_from if e != "*"]

    owner_list = list(set(explicit_owners)) if explicit_owners else []

    sender_candidates: list[str] = []
    if sender_id:
        sender_candidates.append(sender_id)
    if sender_e164 and sender_e164 != sender_id:
        sender_candidates.append(sender_e164)
    if not sender_candidates and from_:
        sender_candidates.append(from_)

    matched_sender = next((c for c in sender_candidates if c in owner_list), None) if owner_list else None
    resolved_sender = matched_sender or (sender_candidates[0] if sender_candidates else None)

    sender_is_owner = bool(matched_sender) or owner_all
    is_authorized = command_authorized and (
        not owner_list or sender_is_owner or allow_all
    )

    return CommandAuthorization(
        provider_id=None,
        owner_list=owner_list,
        sender_id=resolved_sender,
        sender_is_owner=sender_is_owner,
        is_authorized_sender=is_authorized,
        from_=from_ or None,
        to=to or None,
    )
