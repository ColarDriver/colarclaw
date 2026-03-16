from __future__ import annotations

import json

import pytest

from src.api.ws.chat_stream import _merge_provider_configs
from src.container import build_container
from src.core.config import load_settings
from src.llm.providers import (
    AnthropicProvider,
    OpenAICompatibleProvider,
    list_provider_aliases,
    list_registered_provider_ids,
    resolve_provider,
)


def test_resolve_provider_prefers_saved_config_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "env-openrouter-key")
    provider = resolve_provider(
        "openrouter/gpt-4o-mini",
        {
            "openrouter": {
                "apiKey": "saved-openrouter-key",
                "baseUrl": "https://openrouter.example/api/v1",
            }
        },
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert getattr(provider, "_api_key") == "saved-openrouter-key"
    assert getattr(provider, "_base_url") == "https://openrouter.example/api/v1"


def test_resolve_provider_alias_claude_uses_canonical_anthropic_config() -> None:
    provider = resolve_provider(
        "claude/claude-sonnet-4-6",
        {
            "anthropic": {
                "apiKey": "saved-anthropic-key",
                "baseUrl": "https://anthropic.example/v1",
            }
        },
    )
    assert isinstance(provider, AnthropicProvider)
    assert getattr(provider, "_api_key") == "saved-anthropic-key"
    assert getattr(provider, "_base_url") == "https://anthropic.example/v1"


def test_resolve_provider_custom_openai_protocol() -> None:
    provider = resolve_provider(
        "my-openai/custom-model",
        {
            "my-openai": {
                "api": "openai-completions",
                "apiKey": "custom-openai-key",
                "baseUrl": "https://custom-provider.example/v1",
            }
        },
    )
    assert isinstance(provider, OpenAICompatibleProvider)
    assert getattr(provider, "_api_key") == "custom-openai-key"
    assert getattr(provider, "_base_url") == "https://custom-provider.example/v1"


def test_resolve_provider_kimi_base_url_auto_appends_v1() -> None:
    provider = resolve_provider(
        "kimi-coding/kimi-for-coding",
        {
            "kimi-coding": {
                "apiKey": "kimi-key",
                "baseUrl": "https://api.kimi.com/coding/",
            }
        },
    )
    assert isinstance(provider, AnthropicProvider)
    assert getattr(provider, "_base_url") == "https://api.kimi.com/coding/v1"


def test_resolve_provider_kimi_uses_anthropic_env_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("KIMI_API_KEY", "env-kimi-key")
    monkeypatch.setenv("KIMI_BASE_URL", "https://api.kimi.com/coding/")
    provider = resolve_provider("kimi-coding/kimi-for-coding")
    assert isinstance(provider, AnthropicProvider)
    assert getattr(provider, "_api_key") == "env-kimi-key"
    assert getattr(provider, "_base_url") == "https://api.kimi.com/coding/v1"


def test_runtime_provider_ids_hide_aliases_and_echo_when_requested() -> None:
    ids = list_registered_provider_ids(include_aliases=False, include_echo=False)
    assert "anthropic" in ids
    assert "google" in ids
    assert "claude" not in ids
    assert "gemini" not in ids
    assert "echo" not in ids

    aliases = list_provider_aliases()
    assert aliases.get("anthropic") == ["claude"]
    assert aliases.get("google") == ["gemini"]


def test_merge_provider_configs_keeps_api_key_when_omitted() -> None:
    merged = _merge_provider_configs(
        {
            "openrouter": {
                "apiKey": "persist-me",
                "baseUrl": "https://old.example/v1",
            }
        },
        [
            {
                "id": "openrouter",
                "baseUrl": "https://new.example/v1",
            }
        ],
    )
    assert merged["openrouter"]["apiKey"] == "persist-me"
    assert merged["openrouter"]["baseUrl"] == "https://new.example/v1"


def test_merge_provider_configs_clears_api_key_on_empty_string() -> None:
    merged = _merge_provider_configs(
        {
            "openrouter": {
                "apiKey": "remove-me",
                "baseUrl": "https://stay.example/v1",
            }
        },
        [{"id": "openrouter", "apiKey": ""}],
    )
    assert "apiKey" not in merged["openrouter"]
    assert merged["openrouter"]["baseUrl"] == "https://stay.example/v1"


def test_merge_provider_configs_maps_alias_to_canonical() -> None:
    merged = _merge_provider_configs({}, [{"id": "claude", "apiKey": "key-from-alias"}])
    assert "anthropic" in merged
    assert "claude" not in merged


def test_merge_provider_configs_rejects_unknown_custom_api() -> None:
    with pytest.raises(ValueError):
        _merge_provider_configs({}, [{"id": "my-custom", "api": "unknown-protocol"}])


def test_container_loads_provider_configs_from_config_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    config_path = tmp_path / "colarcore.json"
    config_path.write_text(
        json.dumps(
            {
                "agents": {
                    "defaults": {
                        "model": "kimi-coding/k2p5",
                        "fallbackModels": ["openai/gpt-5-mini"],
                    }
                },
                "models": {
                    "registry": ["kimi-coding/k2p5=Kimi 2.5"],
                    "providers": {
                        "kimi-coding": {
                            "apiKey": "kimi-test-key",
                            "baseUrl": "https://api.moonshot.cn/v1",
                        }
                    },
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("COLARCORE_CONFIG", str(config_path))

    container = build_container(load_settings())
    provider_configs = container.runtime_config.get("providerConfigs")
    assert isinstance(provider_configs, dict)
    assert "kimi-coding" in provider_configs
    kimi_entry = provider_configs["kimi-coding"]
    assert isinstance(kimi_entry, dict)
    assert kimi_entry.get("apiKey") == "kimi-test-key"
    assert container.runtime_config.get("defaultModel") == "kimi-coding/k2p5"
    registry = container.runtime_config.get("modelRegistry")
    assert isinstance(registry, tuple)
    assert any(item.split("=", 1)[0].strip() == "kimi-coding/k2p5" for item in registry)
    assert any(item.split("=", 1)[0].strip() == "openai/gpt-5-mini" for item in registry)
