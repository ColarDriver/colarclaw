from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from main import create_app


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer openclaw-dev-token"}


def _ws_connect(ws) -> None:
    ws.send_json(
        {
            "type": "req",
            "id": "connect-1",
            "method": "connect",
            "params": {"auth": {"token": "openclaw-dev-token"}},
        }
    )
    frame = ws.receive_json()
    assert frame["type"] == "res"
    assert frame["id"] == "connect-1"
    assert frame["ok"] is True


def _ws_call(ws, req_id: str, method: str, params: dict[str, object]) -> dict[str, object]:
    ws.send_json({"type": "req", "id": req_id, "method": method, "params": params})
    while True:
        frame = ws.receive_json()
        if frame.get("type") != "res":
            continue
        if frame.get("id") != req_id:
            continue
        return frame


def test_healthz() -> None:
    client = TestClient(create_app())
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_session_and_chat_flow() -> None:
    client = TestClient(create_app())

    create_resp = client.post("/v1/sessions", json={"title": "Flow"}, headers=_headers())
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session"]["id"]

    chat_resp = client.post(
        "/v1/chat/runs",
        json={"sessionId": session_id, "message": "hello", "idempotencyKey": "idem-1"},
        headers=_headers(),
    )
    assert chat_resp.status_code == 200
    assert chat_resp.json()["run"]["text"]

    dedup_resp = client.post(
        "/v1/chat/runs",
        json={"sessionId": session_id, "message": "hello", "idempotencyKey": "idem-1"},
        headers=_headers(),
    )
    assert dedup_resp.status_code == 200
    assert dedup_resp.json()["run"]["deduplicated"] is True

    detail_resp = client.get(f"/v1/sessions/{session_id}", headers=_headers())
    assert detail_resp.status_code == 200
    assert len(detail_resp.json()["session"]["messages"]) >= 2


def test_abort_unknown_run_returns_404() -> None:
    client = TestClient(create_app())
    resp = client.post("/v1/chat/runs/run_unknown/abort", headers=_headers())
    assert resp.status_code == 404


def test_settings_hot_reload_tool_policy() -> None:
    # Disable exception passthrough so we can assert the HTTP status code.
    client = TestClient(create_app(), raise_server_exceptions=False)

    set_resp = client.put(
        "/v1/settings",
        json={
            "toolAllowlist": ["clock.now"],
            "toolDenylist": [],
            "maxToolCallsPerRun": 4,
            "maxSameToolRepeat": 3,
            "maxToolCallsPerMinute": 60,
        },
        headers=_headers(),
    )
    assert set_resp.status_code == 200

    # /tool echo requires echo.text; should now fail in live policy.
    flow_resp = client.post("/v1/sessions", json={"title": "Policy"}, headers=_headers())
    session_id = flow_resp.json()["session"]["id"]
    chat_resp = client.post(
        "/v1/chat/runs",
        json={"sessionId": session_id, "message": "/tool echo hi"},
        headers=_headers(),
    )
    assert chat_resp.status_code == 500


def test_model_registry_blocks_unknown_model() -> None:
    client = TestClient(create_app())

    flow_resp = client.post("/v1/sessions", json={"title": "Model Guard"}, headers=_headers())
    session_id = flow_resp.json()["session"]["id"]
    chat_resp = client.post(
        "/v1/chat/runs",
        json={"sessionId": session_id, "message": "hello", "model": "openai/not-registered"},
        headers=_headers(),
    )
    assert chat_resp.status_code == 400
    assert "model not registered" in chat_resp.text


def test_runtime_endpoint_lists_skills_models_and_mcp() -> None:
    client = TestClient(create_app())

    resp = client.get("/v1/runtime", headers=_headers())
    assert resp.status_code == 200
    payload = resp.json()["runtime"]
    assert isinstance(payload["modelRegistry"], list)
    assert isinstance(payload["mcpServers"], list)
    assert isinstance(payload["skillsAvailable"], list)


def test_ws_connect_and_chat_send() -> None:
    client = TestClient(create_app())
    with client.websocket_connect("/v1/ws/chat?token=openclaw-dev-token") as ws:
        _ws_connect(ws)
        res = _ws_call(
            ws,
            "chat-send-1",
            "chat.send",
            {"sessionKey": "ws-main", "message": "time"},
        )
        assert res["ok"] is True
        payload = res["payload"]
        assert payload["accepted"] is True
        assert isinstance(payload["runId"], str) and payload["runId"]


def test_ws_chat_send_new_resets_session() -> None:
    client = TestClient(create_app())
    create_resp = client.post("/v1/sessions", json={"title": "WS Reset"}, headers=_headers())
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session"]["id"]

    chat_resp = client.post(
        "/v1/chat/runs",
        json={"sessionId": session_id, "message": "seed"},
        headers=_headers(),
    )
    assert chat_resp.status_code == 200

    with client.websocket_connect("/v1/ws/chat?token=openclaw-dev-token") as ws:
        _ws_connect(ws)

        history_before = _ws_call(
            ws,
            "history-before-reset",
            "chat.history",
            {"sessionKey": session_id},
        )
        assert history_before["ok"] is True
        before_messages = history_before["payload"]["messages"]
        assert isinstance(before_messages, list) and len(before_messages) >= 2

        reset_res = _ws_call(
            ws,
            "chat-send-reset",
            "chat.send",
            {"sessionKey": session_id, "message": "/new", "idempotencyKey": "ws-reset-idem"},
        )
        assert reset_res["ok"] is True
        assert reset_res["payload"]["accepted"] is True
        assert reset_res["payload"]["runId"] == "ws-reset-idem"
        assert reset_res["payload"]["reason"] == "new"
        assert reset_res["payload"]["reset"] is True

        history_after = _ws_call(
            ws,
            "history-after-reset",
            "chat.history",
            {"sessionKey": session_id},
        )
        assert history_after["ok"] is True
        after_messages = history_after["payload"]["messages"]
        assert isinstance(after_messages, list)
        assert after_messages == []


def test_ws_models_providers_get_apply_delete(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "openclaw.json"
    monkeypatch.setenv("OPENCLAW_CONFIG", str(config_path))

    client = TestClient(create_app())
    with client.websocket_connect("/v1/ws/chat?token=openclaw-dev-token") as ws:
        _ws_connect(ws)

        get_before = _ws_call(ws, "models-get-before", "models.providers.get", {})
        assert get_before["ok"] is True
        before_payload = get_before["payload"]
        assert isinstance(before_payload.get("catalog", {}).get("providers"), list)

        apply_payload = {
            "defaults": {
                "defaultModel": "openrouter/gpt-5.4",
                "fallbackModels": ["openai/gpt-5-mini"],
            },
            "modelRegistry": [
                "openrouter/gpt-5.4=GPT 5.4",
                "openai/gpt-5-mini=GPT 5 Mini",
            ],
            "providers": [
                {
                    "id": "openrouter",
                    "baseUrl": "https://openrouter.ai/api/v1",
                    "apiKey": "openrouter-test-key",
                    "models": ["openrouter/gpt-5.4"],
                },
                {
                    "id": "claude",
                    "apiKey": "anthropic-test-key",
                },
                {
                    "id": "custom-provider",
                    "kind": "custom",
                    "api": "openai-completions",
                    "baseUrl": "https://custom.example/v1",
                    "apiKey": "custom-provider-key",
                    "models": ["custom-provider/my-model"],
                },
            ],
        }
        apply_res = _ws_call(
            ws,
            "models-apply",
            "models.providers.apply",
            apply_payload,
        )
        assert apply_res["ok"] is True
        assert apply_res["payload"]["ok"] is True

        get_after = _ws_call(ws, "models-get-after", "models.providers.get", {})
        assert get_after["ok"] is True
        after_payload = get_after["payload"]
        assert after_payload["defaults"]["defaultModel"] == "openrouter/gpt-5.4"
        assert after_payload["defaults"]["fallbackModels"] == ["openai/gpt-5-mini"]
        assert after_payload["modelRegistry"] == [
            "openrouter/gpt-5.4=GPT 5.4",
            "openai/gpt-5-mini=GPT 5 Mini",
        ]

        providers = {entry["id"]: entry for entry in after_payload["providers"]}
        assert "openrouter" in providers
        assert "anthropic" in providers
        assert "custom-provider" in providers
        assert providers["openrouter"]["apiKeyConfigured"] is True
        assert providers["openrouter"]["apiKeyPreview"]
        assert "openrouter-test-key" not in providers["openrouter"]["apiKeyPreview"]

        delete_res = _ws_call(
            ws,
            "models-delete-custom",
            "models.providers.delete",
            {"providerId": "custom-provider"},
        )
        assert delete_res["ok"] is True
        assert delete_res["payload"]["ok"] is True

        get_final = _ws_call(ws, "models-get-final", "models.providers.get", {})
        final_providers = {entry["id"]: entry for entry in get_final["payload"]["providers"]}
        assert "custom-provider" not in final_providers


def test_memory_tool_endpoints_via_chat_flow() -> None:
    client = TestClient(create_app())

    create_resp = client.post("/v1/sessions", json={"title": "Memory Tool"}, headers=_headers())
    assert create_resp.status_code == 200
    session_id = create_resp.json()["session"]["id"]

    chat_resp = client.post(
        "/v1/chat/runs",
        json={"sessionId": session_id, "message": "remember I use postgres", "idempotencyKey": "mem-1"},
        headers=_headers(),
    )
    assert chat_resp.status_code == 200

    # second message should retrieve structured context rows
    follow_up = client.post(
        "/v1/chat/runs",
        json={"sessionId": session_id, "message": "what database do I use", "idempotencyKey": "mem-2"},
        headers=_headers(),
    )
    assert follow_up.status_code == 200
    context = follow_up.json()["run"]["retrievedContext"]
    assert isinstance(context, list)
    if context:
        first = context[0]
        assert "path" in first and "snippet" in first and "score" in first


def test_runtime_memory_qmd_keys_are_round_trippable() -> None:
    client = TestClient(create_app())

    put_resp = client.put(
        "/v1/runtime",
        json={"memory": {"backend": "qmd", "qmdCommand": "qmd-cli", "qmdTimeoutMs": 12345, "qmdMaxInjectedChars": 4096}},
        headers=_headers(),
    )
    assert put_resp.status_code == 200

    runtime = put_resp.json()["runtime"]
    assert runtime["memory"]["backend"] == "qmd"
    assert runtime["memory"]["qmdCommand"] == "qmd-cli"
    assert runtime["memory"]["qmdTimeoutMs"] == 12345
    assert runtime["memory"]["qmdMaxInjectedChars"] == 4096



def test_qmd_manager_normalizes_score_and_clamps_budget() -> None:
    from memory.qmd_manager import QmdConfig, QmdMemoryManager

    manager = QmdMemoryManager(
        QmdConfig(
            command="qmd-cli",
            timeout_ms=1000,
            max_results=5,
            min_score=0.0,
            max_injected_chars=10,
        )
    )

    payload = [
        {
            "path": "memory/foo.md",
            "startLine": 1,
            "endLine": 3,
            "score": -3.0,
            "snippet": "abcdefghijklmnop",
            "source": "memory",
        }
    ]

    manager._run_qmd = lambda args, body: __import__("json").dumps({"rows": payload})  # type: ignore[attr-defined]

    results = manager.search("foo")
    assert len(results) == 1
    assert 0.7 < results[0].score < 0.8
    assert results[0].snippet == "abcdefghij"



def test_memory_watch_reason_debounces_sync() -> None:
    from memory.config import resolve_memory_search_config
    from memory.manager import MemoryIndexManager
    from core.config import load_settings

    settings = load_settings()
    runtime = {
        "memory": {
            "enabled": True,
            "backend": "builtin",
            "sources": ["memory"],
            "syncWatch": True,
            "syncWatchDebounceMs": 100,
            "syncOnSearch": False,
        }
    }

    manager = MemoryIndexManager(resolve_memory_search_config(settings, runtime))

    calls: list[str | None] = []
    original_sync = manager.sync

    def _spy_sync(*, reason=None, force=False, progress=None):
        calls.append(reason)
        return original_sync(reason=reason, force=force, progress=progress)

    manager.sync = _spy_sync  # type: ignore[method-assign]
    manager.mark_dirty(reason="watch")

    import time

    time.sleep(0.25)
    manager.close()

    assert "watch" in calls
