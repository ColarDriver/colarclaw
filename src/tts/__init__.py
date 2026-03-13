"""TTS — Text to Speech.

Ported from bk/src/tts/ (~2 TS files).

Covers TTS provider abstraction and audio generation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class TTSConfig:
    provider: str = "elevenlabs"  # "elevenlabs" | "openai" | "google" | "system"
    voice_id: str = ""
    model: str = ""
    speed: float = 1.0
    enabled: bool = False


@dataclass
class TTSResult:
    audio_path: str = ""
    audio_url: str = ""
    duration_ms: int = 0
    mime_type: str = "audio/mpeg"


async def synthesize_speech(
    text: str,
    config: TTSConfig,
    *,
    output_dir: str = "/tmp",
) -> TTSResult | None:
    """Synthesize speech from text."""
    if not config.enabled:
        return None
    if not text.strip():
        return None

    if config.provider == "elevenlabs":
        return await _elevenlabs_tts(text, config, output_dir)
    elif config.provider == "openai":
        return await _openai_tts(text, config, output_dir)
    else:
        logger.warning(f"Unknown TTS provider: {config.provider}")
        return None


async def _elevenlabs_tts(text: str, config: TTSConfig, output_dir: str) -> TTSResult | None:
    """ElevenLabs TTS."""
    try:
        import aiohttp, os
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{config.voice_id or 'default'}"
        api_key = os.environ.get("ELEVENLABS_API_KEY", "")
        if not api_key:
            return None
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"text": text, "model_id": config.model or "eleven_monolingual_v1"},
                                   headers={"xi-api-key": api_key}) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
                path = os.path.join(output_dir, f"tts-{hash(text) % 100000}.mp3")
                with open(path, "wb") as f:
                    f.write(data)
                return TTSResult(audio_path=path, duration_ms=len(data) // 16)
    except Exception as e:
        logger.error(f"ElevenLabs TTS error: {e}")
        return None


async def _openai_tts(text: str, config: TTSConfig, output_dir: str) -> TTSResult | None:
    """OpenAI TTS."""
    try:
        import aiohttp, os
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            return None
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://api.openai.com/v1/audio/speech",
                json={"model": config.model or "tts-1", "input": text, "voice": config.voice_id or "alloy"},
                headers={"Authorization": f"Bearer {api_key}"},
            ) as resp:
                if resp.status != 200:
                    return None
                data = await resp.read()
                path = os.path.join(output_dir, f"tts-{hash(text) % 100000}.mp3")
                with open(path, "wb") as f:
                    f.write(data)
                return TTSResult(audio_path=path, duration_ms=len(data) // 16)
    except Exception as e:
        logger.error(f"OpenAI TTS error: {e}")
        return None


def resolve_tts_config(config: dict[str, Any]) -> TTSConfig:
    tts = config.get("tts", {}) or {}
    return TTSConfig(
        provider=tts.get("provider", "elevenlabs"),
        voice_id=str(tts.get("voiceId", "")),
        model=str(tts.get("model", "")),
        speed=float(tts.get("speed", 1.0)),
        enabled=bool(tts.get("enabled", False)),
    )
