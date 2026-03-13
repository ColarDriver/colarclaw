"""Channels reply_prefix — ported from bk/src/channels/reply-prefix.ts.

Reply prefix context building for agent responses.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class ReplyPrefixContextBundle:
    channel: str = ""
    agent_id: str = ""
    agent_name: str = ""
    model_id: str = ""
    model_label: str = ""
    is_auto_selected: bool = False


@dataclass
class ReplyPrefixOptions:
    include_model_info: bool = False
    include_agent_name: bool = False
    include_channel: bool = False
    prefix_template: str = ""


def create_reply_prefix_context(
    cfg: dict[str, Any],
    channel: str = "",
    agent_id: str = "",
    agent_name: str = "",
    model_id: str = "",
    model_label: str = "",
    is_auto_selected: bool = False,
) -> ReplyPrefixContextBundle:
    """Build context for a reply prefix."""
    return ReplyPrefixContextBundle(
        channel=channel,
        agent_id=agent_id,
        agent_name=agent_name or agent_id,
        model_id=model_id,
        model_label=model_label or model_id,
        is_auto_selected=is_auto_selected,
    )


def create_reply_prefix_options(
    cfg: dict[str, Any],
    channel: str = "",
) -> ReplyPrefixOptions:
    """Build options for reply prefix formatting."""
    channel_cfg = cfg.get("channels", {}).get(channel, {})
    reply_cfg = channel_cfg.get("replyPrefix", {})
    return ReplyPrefixOptions(
        include_model_info=reply_cfg.get("includeModelInfo", False),
        include_agent_name=reply_cfg.get("includeAgentName", False),
        include_channel=reply_cfg.get("includeChannel", False),
        prefix_template=reply_cfg.get("template", ""),
    )


def format_reply_prefix(
    context: ReplyPrefixContextBundle,
    options: ReplyPrefixOptions,
) -> str:
    """Format a reply prefix from context and options."""
    parts: list[str] = []
    if options.include_agent_name and context.agent_name:
        parts.append(f"[{context.agent_name}]")
    if options.include_model_info and context.model_label:
        label = context.model_label
        if context.is_auto_selected:
            label += " (auto)"
        parts.append(f"({label})")
    if options.include_channel and context.channel:
        parts.append(f"via {context.channel}")
    if options.prefix_template:
        return options.prefix_template.format(
            agent=context.agent_name,
            model=context.model_label,
            channel=context.channel,
        )
    return " ".join(parts)
