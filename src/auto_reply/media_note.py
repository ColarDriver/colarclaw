"""Auto-reply media note — ported from bk/src/auto-reply/media-note.ts.

Build [media attached: ...] annotations for inbound messages.
"""
from __future__ import annotations

from typing import Any

AUDIO_EXTENSIONS = frozenset([
    ".ogg", ".opus", ".mp3", ".m4a", ".wav", ".webm", ".flac",
    ".aac", ".wma", ".aiff", ".alac", ".oga",
])


def _is_audio_path(path: str | None) -> bool:
    if not path:
        return False
    lower = path.lower()
    return any(lower.endswith(ext) for ext in AUDIO_EXTENSIONS)


def _format_media_attached_line(
    path: str,
    url: str | None = None,
    type_: str | None = None,
    index: int | None = None,
    total: int | None = None,
) -> str:
    prefix = f"[media attached {index}/{total}: " if index is not None and total is not None else "[media attached: "
    type_part = f" ({type_.strip()})" if type_ and type_.strip() else ""
    url_raw = url.strip() if url else ""
    url_part = f" | {url_raw}" if url_raw else ""
    return f"{prefix}{path}{type_part}{url_part}]"


def build_inbound_media_note(ctx: Any) -> str | None:
    suppressed: set[int] = set()
    transcribed_audio: set[int] = set()

    media_understanding = getattr(ctx, "MediaUnderstanding", None)
    if isinstance(media_understanding, list):
        for output in media_understanding:
            idx = getattr(output, "attachmentIndex", getattr(output, "attachment_index", None))
            if idx is not None:
                suppressed.add(idx)
                kind = getattr(output, "kind", "")
                if kind == "audio.transcription":
                    transcribed_audio.add(idx)

    media_decisions = getattr(ctx, "MediaUnderstandingDecisions", None)
    if isinstance(media_decisions, list):
        for decision in media_decisions:
            if getattr(decision, "outcome", "") != "success":
                continue
            attachments = getattr(decision, "attachments", [])
            for att in attachments:
                chosen = getattr(att, "chosen", None)
                if chosen and getattr(chosen, "outcome", "") == "success":
                    att_idx = getattr(att, "attachmentIndex", getattr(att, "attachment_index", None))
                    if att_idx is not None:
                        suppressed.add(att_idx)
                        if getattr(decision, "capability", "") == "audio":
                            transcribed_audio.add(att_idx)

    paths_array = getattr(ctx, "MediaPaths", None)
    if isinstance(paths_array, list) and len(paths_array) > 0:
        paths = paths_array
    else:
        single = getattr(ctx, "MediaPath", None)
        paths = [single.strip()] if single and isinstance(single, str) and single.strip() else []

    if not paths:
        return None

    urls = getattr(ctx, "MediaUrls", None)
    urls = urls if isinstance(urls, list) and len(urls) == len(paths) else None
    types = getattr(ctx, "MediaTypes", None)
    types = types if isinstance(types, list) and len(types) == len(paths) else None

    has_transcript = bool(getattr(ctx, "Transcript", None) and getattr(ctx, "Transcript", "").strip())
    can_strip_single_by_transcript = has_transcript and len(paths) == 1

    entries = []
    for i, p in enumerate(paths):
        if i in suppressed:
            continue
        type_ = types[i] if types else getattr(ctx, "MediaType", None)
        has_per_entry_type = types is not None
        is_audio_by_mime = has_per_entry_type and type_ and str(type_).lower().startswith("audio/")
        is_audio = _is_audio_path(p) or is_audio_by_mime
        if is_audio:
            if i in transcribed_audio or (can_strip_single_by_transcript and i == 0):
                continue
        entries.append({
            "path": p or "",
            "type": type_,
            "url": urls[i] if urls else getattr(ctx, "MediaUrl", None),
            "index": i,
        })

    if not entries:
        return None
    if len(entries) == 1:
        e = entries[0]
        return _format_media_attached_line(e["path"], e.get("url"), e.get("type"))

    count = len(entries)
    lines = [f"[media attached: {count} files]"]
    for idx, e in enumerate(entries):
        lines.append(_format_media_attached_line(
            e["path"], e.get("url"), e.get("type"),
            index=idx + 1, total=count,
        ))
    return "\n".join(lines)
