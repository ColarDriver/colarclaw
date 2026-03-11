"""Reply audio tags — ported from bk/src/auto-reply/reply/audio-tags.ts."""
from __future__ import annotations


AUDIO_TAG_PATTERN = r"\[audio:\s*([^\]]+)\]"

def strip_audio_tags(text: str) -> str:
    import re
    return re.sub(AUDIO_TAG_PATTERN, "", text).strip()


def extract_audio_tags(text: str) -> list[str]:
    import re
    return re.findall(AUDIO_TAG_PATTERN, text)
