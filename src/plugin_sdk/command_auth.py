"""Plugin SDK command auth — ported from bk/src/plugin-sdk/command-auth.ts.

DM/group command authorization: sender resolution, access group evaluation.
"""
from __future__ import annotations

from typing import Any, Callable, Literal


AuthorizationOutcome = Literal["disabled", "unauthorized", "allowed"]


def resolve_direct_dm_authorization_outcome(
    is_group: bool, dm_policy: str, sender_allowed_for_commands: bool,
) -> AuthorizationOutcome:
    if is_group:
        return "allowed"
    if dm_policy == "disabled":
        return "disabled"
    if dm_policy != "open" and not sender_allowed_for_commands:
        return "unauthorized"
    return "allowed"


async def resolve_sender_command_authorization(
    cfg: Any,
    raw_body: str,
    is_group: bool,
    dm_policy: str,
    configured_allow_from: list[str],
    sender_id: str,
    is_sender_allowed: Callable[[str, list[str]], bool],
    read_allow_from_store: Callable[..., Any],
    should_compute_command_authorized: Callable[[str, Any], bool],
    resolve_command_authorized_from_authorizers: Callable[..., bool],
    configured_group_allow_from: list[str] | None = None,
) -> dict[str, Any]:
    should_compute = should_compute_command_authorized(raw_body, cfg)
    group_allow = configured_group_allow_from or []

    # Read store allow-from for DM non-allowlist cases
    store_allow_from: list[str] = []
    if not is_group and dm_policy != "allowlist" and (dm_policy != "open" or should_compute):
        try:
            store_allow_from = await read_allow_from_store()
        except Exception:
            store_allow_from = []

    # Build effective lists
    effective_allow_from = list(configured_allow_from)
    if store_allow_from:
        effective_allow_from = list(set(effective_allow_from + store_allow_from))
    effective_group_allow_from = list(group_allow)

    # Evaluate
    target_list = effective_group_allow_from if is_group else effective_allow_from
    sender_allowed = is_sender_allowed(sender_id, target_list)
    owner_allowed = is_sender_allowed(sender_id, effective_allow_from)
    group_allowed = is_sender_allowed(sender_id, effective_group_allow_from)

    use_access_groups = True
    if isinstance(cfg, dict):
        commands = cfg.get("commands", {})
        use_access_groups = commands.get("useAccessGroups", commands.get("use_access_groups", True)) is not False

    command_authorized = None
    if should_compute:
        command_authorized = resolve_command_authorized_from_authorizers(
            use_access_groups=use_access_groups,
            authorizers=[
                {"configured": bool(effective_allow_from), "allowed": owner_allowed},
                {"configured": bool(effective_group_allow_from), "allowed": group_allowed},
            ],
        )

    return {
        "should_compute_auth": should_compute,
        "effective_allow_from": effective_allow_from,
        "effective_group_allow_from": effective_group_allow_from,
        "sender_allowed_for_commands": sender_allowed,
        "command_authorized": command_authorized,
    }


async def resolve_sender_command_authorization_with_runtime(
    cfg: Any, raw_body: str, is_group: bool, dm_policy: str,
    configured_allow_from: list[str], sender_id: str,
    is_sender_allowed: Callable[[str, list[str]], bool],
    read_allow_from_store: Callable[..., Any],
    runtime: dict[str, Any],
    configured_group_allow_from: list[str] | None = None,
) -> dict[str, Any]:
    return await resolve_sender_command_authorization(
        cfg=cfg, raw_body=raw_body, is_group=is_group, dm_policy=dm_policy,
        configured_allow_from=configured_allow_from, sender_id=sender_id,
        is_sender_allowed=is_sender_allowed,
        read_allow_from_store=read_allow_from_store,
        should_compute_command_authorized=runtime.get("should_compute_command_authorized", lambda *_: False),
        resolve_command_authorized_from_authorizers=runtime.get("resolve_command_authorized_from_authorizers", lambda **_: False),
        configured_group_allow_from=configured_group_allow_from,
    )
