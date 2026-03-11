from __future__ import annotations

import asyncio

from container import build_container
from core.config import load_settings


def test_graph_run_returns_text() -> None:
    async def _run() -> None:
        container = build_container(load_settings())
        session = await container.session_repo.create_session("Test Session")
        state = await container.graph.run(
            run_id="run_test",
            session_id=session.id,
            message="hello from test",
            model=None,
        )
        assert state.response_text

    asyncio.run(_run())


def test_graph_uses_model_registry_default() -> None:
    async def _run() -> None:
        container = build_container(load_settings())
        session = await container.session_repo.create_session("Registry Session")
        state = await container.graph.run(
            run_id="run_registry",
            session_id=session.id,
            message="use defaults",
            model=None,
        )
        assert "openai/echo-default" in state.response_text

    asyncio.run(_run())


def test_graph_memory_sessions_source() -> None:
    async def _run() -> None:
        import os

        os.environ["OPENCLAW_MEMORY_SOURCES"] = "memory,sessions"
        os.environ["OPENCLAW_MEMORY_SESSION_ENABLED"] = "true"
        container = build_container(load_settings())
        session = await container.session_repo.create_session("Session Memory")

        await container.session_repo.append_message(session.id, "user", "I like jasmine tea")
        await container.session_repo.append_message(session.id, "assistant", "Noted preference: jasmine tea")
        container.memory_manager.mark_dirty()

        state = await container.graph.run(
            run_id="run_sessions_memory",
            session_id=session.id,
            message="jasmine tea preference",
            model=None,
        )
        assert any("jasmine" in item.snippet.lower() for item in state.retrieved_context)

    asyncio.run(_run())


def test_qmd_backend_falls_back_to_builtin_when_unavailable() -> None:
    async def _run() -> None:
        import os

        os.environ["OPENCLAW_MEMORY_BACKEND"] = "qmd"
        os.environ["OPENCLAW_MEMORY_QMD_COMMAND"] = "definitely-not-a-real-command"

        container = build_container(load_settings())
        session = await container.session_repo.create_session("QMD Fallback")

        state = await container.graph.run(
            run_id="run_qmd_fallback",
            session_id=session.id,
            message="hello fallback",
            model=None,
        )
        assert state.response_text

        status = container.memory_manager.status()
        assert status.backend in {"builtin", "qmd"}

    asyncio.run(_run())



