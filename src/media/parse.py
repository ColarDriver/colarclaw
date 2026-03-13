"""Media parse — ported from bk/src/media/parse.ts.

MEDIA token extraction from text output, audio tag detection.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

MEDIA_TOKEN_RE = re.compile(r"\bMEDIA:\s*`?([^\n]+)`?", re.IGNORECASE)
WINDOWS_DRIVE_RE = re.compile(r"^[a-zA-Z]:[/\\]")
SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
HAS_FILE_EXT = re.compile(r"\.\w{1,10}$")


def normalize_media_source(src: str) -> str:
    return src.replace("file://", "") if src.startswith("file://") else src


def _clean_candidate(raw: str) -> str:
    cleaned = re.sub(r'^[`"\'\[{(]+', "", raw)
    return re.sub(r'[`"\'\\\})\],]+$', "", cleaned)


def _is_likely_local_path(candidate: str) -> bool:
    return (
        candidate.startswith("/") or candidate.startswith("./") or
        candidate.startswith("../") or candidate.startswith("~") or
        bool(WINDOWS_DRIVE_RE.match(candidate)) or candidate.startswith("\\\\") or
        (not SCHEME_RE.match(candidate) and ("/" in candidate or "\\" in candidate))
    )


def _is_valid_media(candidate: str, allow_spaces: bool = False, allow_bare_filename: bool = False) -> bool:
    if not candidate or len(candidate) > 4096:
        return False
    if not allow_spaces and re.search(r"\s", candidate):
        return False
    if re.match(r"^https?://", candidate, re.IGNORECASE):
        return True
    if _is_likely_local_path(candidate):
        return True
    if allow_bare_filename and not SCHEME_RE.match(candidate) and HAS_FILE_EXT.search(candidate):
        return True
    return False


@dataclass
class SplitMediaResult:
    text: str = ""
    media_urls: list[str] | None = None
    media_url: str | None = None
    audio_as_voice: bool | None = None


def split_media_from_output(raw: str) -> SplitMediaResult:
    trimmed_raw = raw.rstrip()
    if not trimmed_raw.strip():
        return SplitMediaResult(text="")
    has_media_token = bool(re.search(r"media:", trimmed_raw, re.IGNORECASE))
    has_audio_tag = "[[" in trimmed_raw
    if not has_media_token and not has_audio_tag:
        return SplitMediaResult(text=trimmed_raw)
    media: list[str] = []
    found_media_token = False
    lines = trimmed_raw.split("\n")
    kept_lines: list[str] = []
    for line in lines:
        trimmed_start = line.lstrip()
        if not trimmed_start.startswith("MEDIA:"):
            kept_lines.append(line)
            continue
        matches = list(MEDIA_TOKEN_RE.finditer(line))
        if not matches:
            kept_lines.append(line)
            continue
        for match in matches:
            payload = match.group(1)
            parts = payload.split()
            for part in parts:
                candidate = normalize_media_source(_clean_candidate(part))
                if _is_valid_media(candidate):
                    media.append(candidate)
                    found_media_token = True
        if not media:
            fallback = normalize_media_source(_clean_candidate(matches[0].group(1)))
            if _is_valid_media(fallback, allow_spaces=True, allow_bare_filename=True):
                media.append(fallback)
                found_media_token = True
    cleaned = "\n".join(kept_lines).strip()
    cleaned = re.sub(r"\n{2,}", "\n", cleaned)
    # Audio tag
    audio_as_voice = None
    audio_tag_re = re.compile(r"\[\[audio_as_voice\]\]", re.IGNORECASE)
    if audio_tag_re.search(cleaned):
        audio_as_voice = True
        cleaned = audio_tag_re.sub("", cleaned).strip()
    if not media:
        return SplitMediaResult(
            text=cleaned if found_media_token or audio_as_voice else trimmed_raw,
            audio_as_voice=audio_as_voice,
        )
    return SplitMediaResult(
        text=cleaned, media_urls=media,
        media_url=media[0] if media else None,
        audio_as_voice=audio_as_voice,
    )
