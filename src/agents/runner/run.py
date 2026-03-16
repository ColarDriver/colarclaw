"""Agent runner — core orchestration for embedded agent runs.

Ported from colarcore/src/agents/pi-embedded-runner/run.ts

This is the main entry point for running agent turns. The runner
handles the full cycle:

1. Retrieve memory context
2. Plan and execute tools
3. Build system prompt (with tool names, skills, context)
4. Call LLM (with fallback) via LlmRouter
5. Persist conversation to memory store

Unlike the original TS which uses a Graph/LangGraph abstraction,
colarcore uses a direct runner pattern — this module follows that
approach.
"""
from __future__ import annotations

import logging
from dataclasses import asdict
from typing import Any, AsyncIterator

from ..system_prompt import ContextFile
from .system_prompt import build_embedded_system_prompt
from .types import AgentRunState, ToolEvent
from ...llm.router import LlmRouter
from ...memory.retriever import MemoryRetriever
from ...memory.store import MemoryStore
from ...memory.types import MemorySearchResult
from ..skills.skills_status import SkillCatalog
from ...tools.middleware import ToolRuntime

logger = logging.getLogger("colarcore.agents.runner")


class AgentRunner:
    """Embedded agent runner: memory → tools → prompt → LLM → store.

    Follows colarcore's pi-embedded-runner pattern rather than a
    graph/workflow abstraction.
    """

    def __init__(
        self,
        *,
        llm_router: LlmRouter,
        memory_store: MemoryStore,
        memory_retriever: MemoryRetriever,
        tool_runtime: ToolRuntime,
        skill_catalog: SkillCatalog,
        skills_enabled: tuple[str, ...] | None,
    ) -> None:
        self._llm_router = llm_router
        self._memory_store = memory_store
        self._memory_retriever = memory_retriever
        self._tool_runtime = tool_runtime
        self._skill_catalog = skill_catalog
        self._skills_enabled = skills_enabled

    # ------------------------------------------------------------------
    # Step 1: memory retrieval
    # ------------------------------------------------------------------

    def _retrieve_context(self, *, session_id: str, message: str) -> list[MemorySearchResult]:
        try:
            return self._memory_retriever.retrieve(session_id=session_id, query=message, limit=6)
        except Exception as exc:
            logger.warning("memory retrieval failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Step 2: tool planning (simple keyword-based, extendable)
    # ------------------------------------------------------------------

    def _plan_tools(self, message: str) -> list[dict[str, object]]:
        plans: list[dict[str, object]] = []
        lowered = message.strip().lower()
        if lowered.startswith("/tool time") or "what time is it" in lowered:
            plans.append({"name": "clock.now", "args": {}})
        if lowered.startswith("/tool echo "):
            tail = message[len("/tool echo "):].strip()
            plans.append({"name": "echo.text", "args": {"text": tail}})
        if "search memory" in lowered or lowered.startswith("/memory "):
            query = message.split(" ", 1)[-1]
            plans.append({"name": "memory.search", "args": {"query": query}})
        return plans

    # ------------------------------------------------------------------
    # Step 3: execute tool plan
    # ------------------------------------------------------------------

    async def _run_tool_plan(self, state: AgentRunState) -> None:
        for plan in state.planned_tools:
            tool_name = str(plan.get("name", ""))
            tool_args = dict(plan.get("args", {}))
            try:
                result = await self._tool_runtime.execute(
                    run_id=state.run_id,
                    tool_name=tool_name,
                    args=tool_args,
                )
                state.tool_events.append(
                    ToolEvent(name=result.name, args=tool_args, result=result.result)
                )
            except Exception as exc:
                logger.warning("tool %s failed: %s", tool_name, exc)
                state.tool_events.append(
                    ToolEvent(name=tool_name, args=tool_args, result=f"[error] {exc}")
                )

    # ------------------------------------------------------------------
    # Step 4: build message list for LLM
    # ------------------------------------------------------------------

    def _build_messages(
        self,
        state: AgentRunState,
        *,
        session_messages: list[dict] | None = None,
    ) -> tuple[str, list[dict]]:
        """Return (system_prompt, messages)."""
        # Build context files from retrieved memory
        context_files = [
            ContextFile(
                path=f"{item.path}#L{item.start_line}-{item.end_line}",
                content=item.snippet,
            )
            for item in state.retrieved_context
        ]

        # Skills section
        active_skills = self._skill_catalog.list(self._skills_enabled)
        skills_prompt = "\n".join(
            f"<skill key=\"{s.key}\"><description>{s.description or s.name}</description>"
            f"<location>{getattr(s, 'path', s.key)}</location></skill>"
            for s in active_skills
        ) if active_skills else ""

        # Collect tool names from registry for the system prompt
        # This mirrors colarcore's: toolNames: params.tools.map((tool) => tool.name)
        tool_names = [t.name for t in self._tool_runtime.registry.list()]

        system_prompt = build_embedded_system_prompt(
            workspace_dir=".",
            tool_names=tool_names,
            skills_prompt=skills_prompt,
            context_files=context_files,
        )

        # Tool results injected as assistant messages with [tool] prefix
        messages: list[dict] = list(session_messages or [])

        # Inject tool outputs before the final user message
        for event in state.tool_events:
            messages.append({
                "role": "assistant",
                "content": f"[tool:{event.name}] {event.result}",
            })

        # Final user message (already in session_messages but add if empty)
        if not messages or messages[-1].get("role") != "user":
            messages.append({"role": "user", "content": state.user_message})

        return system_prompt, messages

    # ------------------------------------------------------------------
    # Main run() entry point
    # ------------------------------------------------------------------

    async def run(
        self,
        *,
        run_id: str,
        session_id: str,
        message: str,
        model: str | None = None,
        session_messages: list[dict] | None = None,
    ) -> AgentRunState:
        """Execute the full agent cycle and return state with response_text."""
        state = AgentRunState(
            run_id=run_id,
            session_id=session_id,
            user_message=message,
            model=model,
        )

        # 1. Retrieve context
        state.retrieved_context = self._retrieve_context(
            session_id=session_id, message=message
        )

        # 2. Plan tools
        state.planned_tools = self._plan_tools(message)

        # 3. Execute tools
        await self._run_tool_plan(state)

        # 4. Build messages + call LLM
        system_prompt, messages = self._build_messages(
            state, session_messages=session_messages
        )
        routed = await self._llm_router.run(
            prompt=message,
            preferred_model=model,
            system_prompt=system_prompt,
            messages=messages,
        )
        state.response_text = routed.text

        # 5. Persist to memory
        try:
            await self._memory_store.write_user_message(session_id, message)
            await self._memory_store.write_assistant_message(session_id, state.response_text)
        except Exception as exc:
            logger.warning("memory store write failed: %s", exc)

        return state

    # ------------------------------------------------------------------
    # Streaming run()
    # ------------------------------------------------------------------

    async def stream(
        self,
        *,
        run_id: str,
        session_id: str,
        message: str,
        model: str | None = None,
        session_messages: list[dict] | None = None,
    ) -> AsyncIterator[str]:
        """Streaming variant – yields text tokens."""
        state = AgentRunState(
            run_id=run_id,
            session_id=session_id,
            user_message=message,
            model=model,
        )
        state.retrieved_context = self._retrieve_context(session_id=session_id, message=message)
        state.planned_tools = self._plan_tools(message)
        await self._run_tool_plan(state)

        system_prompt, messages = self._build_messages(state, session_messages=session_messages)
        full_text = ""

        async def _gen():
            nonlocal full_text
            async for token in self._llm_router.stream(
                prompt=message,
                preferred_model=model,
                system_prompt=system_prompt,
                messages=messages,
            ):
                full_text += token
                yield token
            # persist after streaming completes
            try:
                await self._memory_store.write_user_message(session_id, message)
                await self._memory_store.write_assistant_message(session_id, full_text)
            except Exception as exc:
                logger.warning("memory store write failed (stream): %s", exc)

        return _gen()

    # ------------------------------------------------------------------
    # Runtime updates
    # ------------------------------------------------------------------

    def update_skills_enabled(self, skills_enabled: tuple[str, ...] | None) -> None:
        """Update the skill filter at runtime (called from config/WS handlers)."""
        self._skills_enabled = skills_enabled

    # ------------------------------------------------------------------
    # Payload helpers
    # ------------------------------------------------------------------

    @staticmethod
    def as_payload(state: AgentRunState) -> dict[str, Any]:
        return {
            "runId": state.run_id,
            "sessionId": state.session_id,
            "response": state.response_text,
            "retrievedContext": [
                {
                    "path": item.path,
                    "startLine": item.start_line,
                    "endLine": item.end_line,
                    "score": item.score,
                    "snippet": item.snippet,
                    "source": item.source,
                    "citation": item.citation,
                }
                for item in state.retrieved_context
            ],
            "tools": [asdict(item) for item in state.tool_events],
        }
