"""Media understanding runner — ported from bk/src/media-understanding/runner.ts + runner.entries.ts.

Main entry point: resolves providers, runs capabilities, manages attachment pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .types import (
    MediaAttachment,
    MediaUnderstandingCapability,
    MediaUnderstandingDecision,
    MediaUnderstandingModelDecision,
    MediaUnderstandingOutput,
)


@dataclass
class ActiveMediaModel:
    provider: str = ""
    model: str | None = None


@dataclass
class RunCapabilityResult:
    outputs: list[MediaUnderstandingOutput]
    decision: MediaUnderstandingDecision


def build_provider_registry(overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    from .providers import build_media_understanding_registry
    return build_media_understanding_registry(overrides)


def normalize_media_attachments(ctx: Any) -> list[MediaAttachment]:
    from .attachments import normalize_attachments
    return normalize_attachments(ctx)


def build_model_decision(entry: Any = None, entry_type: str = "provider", outcome: str = "success", reason: str | None = None) -> MediaUnderstandingModelDecision:
    provider = entry.get("provider") if isinstance(entry, dict) else None
    model = entry.get("model") if isinstance(entry, dict) else None
    return MediaUnderstandingModelDecision(
        provider=provider, model=model, type=entry_type,
        outcome=outcome, reason=reason,
    )


def format_decision_summary(decision: MediaUnderstandingDecision) -> str:
    parts = [f"{decision.capability}: {decision.outcome}"]
    for att in decision.attachments:
        if att.chosen:
            parts.append(f"  [{att.attachment_index}] {att.chosen.provider}/{att.chosen.model} -> {att.chosen.outcome}")
        else:
            parts.append(f"  [{att.attachment_index}] no chosen model")
    return "\n".join(parts)


async def run_capability(
    capability: MediaUnderstandingCapability,
    cfg: Any = None,
    ctx: Any = None,
    media: list[MediaAttachment] | None = None,
    agent_dir: str | None = None,
    provider_registry: dict[str, Any] | None = None,
    config: Any = None,
    active_model: ActiveMediaModel | None = None,
) -> RunCapabilityResult:
    """Run a media understanding capability (placeholder)."""
    return RunCapabilityResult(
        outputs=[],
        decision=MediaUnderstandingDecision(capability=capability, outcome="skipped", attachments=[]),
    )


async def resolve_auto_image_model(cfg: Any = None, agent_dir: str | None = None, active_model: ActiveMediaModel | None = None) -> ActiveMediaModel | None:
    """Resolve auto image model (placeholder)."""
    return None
