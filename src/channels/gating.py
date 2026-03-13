"""Channels gating — ported from bk/src/channels/command-gating.ts,
mention-gating.ts, native-command-session-targets.ts.

Command authorization gating, mention-based gating with bypass logic,
and native command session target resolution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


# ─── command-gating.ts ───

@dataclass
class CommandAuthorizer:
    configured: bool = False
    allowed: bool = False


CommandGatingModeWhenAccessGroupsOff = Literal["allow", "deny", "configured"]


def resolve_command_authorized_from_authorizers(
    use_access_groups: bool,
    authorizers: list[CommandAuthorizer],
    mode_when_access_groups_off: CommandGatingModeWhenAccessGroupsOff = "allow",
) -> bool:
    """Resolve whether a command is authorized from a list of authorizers."""
    if not use_access_groups:
        if mode_when_access_groups_off == "allow":
            return True
        if mode_when_access_groups_off == "deny":
            return False
        # "configured" mode
        any_configured = any(a.configured for a in authorizers)
        if not any_configured:
            return True
        return any(a.configured and a.allowed for a in authorizers)
    return any(a.configured and a.allowed for a in authorizers)


@dataclass
class ControlCommandGateResult:
    command_authorized: bool = False
    should_block: bool = False


def resolve_control_command_gate(
    use_access_groups: bool,
    authorizers: list[CommandAuthorizer],
    allow_text_commands: bool,
    has_control_command: bool,
    mode_when_access_groups_off: CommandGatingModeWhenAccessGroupsOff = "allow",
) -> ControlCommandGateResult:
    """Resolve control command gate (should the command be blocked?)."""
    authorized = resolve_command_authorized_from_authorizers(
        use_access_groups, authorizers, mode_when_access_groups_off,
    )
    should_block = allow_text_commands and has_control_command and not authorized
    return ControlCommandGateResult(command_authorized=authorized, should_block=should_block)


# ─── mention-gating.ts ───

@dataclass
class MentionGateResult:
    effective_was_mentioned: bool = False
    should_skip: bool = False


@dataclass
class MentionGateWithBypassResult(MentionGateResult):
    should_bypass_mention: bool = False


def resolve_mention_gating(
    require_mention: bool,
    can_detect_mention: bool,
    was_mentioned: bool,
    implicit_mention: bool = False,
    should_bypass_mention: bool = False,
) -> MentionGateResult:
    """Resolve mention gating: should this message be skipped?"""
    effective = was_mentioned or implicit_mention or should_bypass_mention
    should_skip = require_mention and can_detect_mention and not effective
    return MentionGateResult(effective_was_mentioned=effective, should_skip=should_skip)


def resolve_mention_gating_with_bypass(
    is_group: bool,
    require_mention: bool,
    can_detect_mention: bool,
    was_mentioned: bool,
    allow_text_commands: bool,
    has_control_command: bool,
    command_authorized: bool,
    implicit_mention: bool = False,
    has_any_mention: bool = False,
) -> MentionGateWithBypassResult:
    """Resolve mention gating with command-bypass logic for groups."""
    should_bypass = (
        is_group and require_mention and not was_mentioned
        and not has_any_mention and allow_text_commands
        and command_authorized and has_control_command
    )
    gate = resolve_mention_gating(
        require_mention=require_mention,
        can_detect_mention=can_detect_mention,
        was_mentioned=was_mentioned,
        implicit_mention=implicit_mention,
        should_bypass_mention=should_bypass,
    )
    return MentionGateWithBypassResult(
        effective_was_mentioned=gate.effective_was_mentioned,
        should_skip=gate.should_skip,
        should_bypass_mention=should_bypass,
    )


# ─── native-command-session-targets.ts ───

def resolve_native_command_session_target(
    channel: str,
    target_id: str | None = None,
    group_id: str | None = None,
) -> str | None:
    """Resolve the session target for a native command invocation."""
    if target_id:
        return target_id.strip() or None
    if group_id:
        return group_id.strip() or None
    return None
