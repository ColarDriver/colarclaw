from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_auth_context, get_container
from graph.main_graph import GraphOrchestrator
from mcp.registry import parse_mcp_servers
from memory.manager import SessionMemoryRecord
from memory.retriever import MemoryRetriever
from memory.search_manager import get_memory_search_manager
from memory.store import MemoryStore
from models.registry import parse_registered_model_entries
from schemas.settings import SettingsView, UpdateSettingsRequest
from tools.registry import create_default_registry

router = APIRouter(prefix="/v1/settings", tags=["settings"])


def _view(container) -> SettingsView:
    return SettingsView(
        defaultModel=container.runtime_config["defaultModel"],
        fallbackModels=list(container.runtime_config["fallbackModels"]),
        toolAllowlist=list(container.runtime_config["toolAllowlist"]),
        toolDenylist=list(container.runtime_config.get("toolDenylist", ())),
        maxToolCallsPerRun=int(container.runtime_config.get("maxToolCallsPerRun", 4)),
        maxSameToolRepeat=int(container.runtime_config.get("maxSameToolRepeat", 3)),
        maxToolCallsPerMinute=int(container.runtime_config.get("maxToolCallsPerMinute", 60)),
        modelRegistry=list(container.runtime_config.get("modelRegistry", ())),
        mcpServers=list(container.runtime_config.get("mcpServers", ())),
        skillsEnabled=list(container.runtime_config.get("skillsEnabled", ())),
    )


def _apply_tool_policy_runtime(container) -> None:
    container.tool_runtime.update_policy(
        allowlist=tuple(container.runtime_config.get("toolAllowlist", ())),
        denylist=tuple(container.runtime_config.get("toolDenylist", ())),
        max_calls_per_run=int(container.runtime_config.get("maxToolCallsPerRun", 4)),
        max_same_tool_repeat=int(container.runtime_config.get("maxSameToolRepeat", 3)),
        max_calls_per_minute=int(container.runtime_config.get("maxToolCallsPerMinute", 60)),
    )


def _apply_model_runtime(container) -> None:
    default_model = str(container.runtime_config.get("defaultModel", "")).strip()
    fallback_models = tuple(container.runtime_config.get("fallbackModels", ()))
    model_entries = tuple(container.runtime_config.get("modelRegistry", ()))
    container.model_registry.replace(parse_registered_model_entries(model_entries))
    container.llm_router.update_models(default_model=default_model, fallback_models=fallback_models)


def _apply_mcp_runtime(container) -> None:
    mcp_entries = tuple(container.runtime_config.get("mcpServers", ()))
    container.mcp_registry.replace(parse_mcp_servers(mcp_entries))


def _build_session_records_provider(container):
    def _provider() -> list[SessionMemoryRecord]:
        rows: list[SessionMemoryRecord] = []
        if hasattr(container.session_repo, "_messages"):
            messages_map = getattr(container.session_repo, "_messages", {})
            for _session_id, messages in messages_map.items():
                for msg in messages:
                    rows.append(
                        SessionMemoryRecord(
                            session_id=msg.session_id,
                            role=msg.role,
                            text=msg.text,
                            created_at_ms=msg.created_at_ms,
                        )
                    )
        return rows

    return _provider


def _apply_memory_runtime(container) -> None:
    provider = _build_session_records_provider(container)
    resolved = get_memory_search_manager(
        settings=container.settings,
        runtime_config=container.runtime_config,
        session_records_provider=provider,
    )
    if resolved.manager is None:
        raise RuntimeError(resolved.error or "memory manager unavailable")

    if resolved.manager is not container.memory_manager:
        container.memory_manager.close()
        container.memory_manager = resolved.manager
        container.memory_store = MemoryStore(container.session_repo, resolved.manager)
        container.memory_retriever = MemoryRetriever(resolved.manager)
        container.graph = GraphOrchestrator(
            llm_router=container.llm_router,
            memory_store=container.memory_store,
            memory_retriever=container.memory_retriever,
            tool_runtime=container.tool_runtime,
            skill_catalog=container.skill_catalog,
            skills_enabled=tuple(container.runtime_config.get("skillsEnabled", ())),
        )

    container.memory_manager.attach_session_records_provider(provider)
    container.tool_registry = create_default_registry(settings=container.settings, runtime_config=container.runtime_config)
    container.tool_runtime._registry = container.tool_registry


def _apply_skills_runtime(container) -> None:
    container.skill_catalog.reload()
    skills_enabled = tuple(container.runtime_config.get("skillsEnabled", ()))
    container.graph.update_skills_enabled(skills_enabled)


@router.get("")
async def get_settings(container=Depends(get_container), _auth=Depends(get_auth_context)) -> dict[str, object]:
    return {"settings": _view(container).model_dump()}


@router.put("")
async def put_settings(
    body: UpdateSettingsRequest,
    container=Depends(get_container),
    _auth=Depends(get_auth_context),
) -> dict[str, object]:
    if body.defaultModel is not None:
        container.runtime_config["defaultModel"] = body.defaultModel
    if body.fallbackModels is not None:
        container.runtime_config["fallbackModels"] = tuple(body.fallbackModels)
    if body.toolAllowlist is not None:
        container.runtime_config["toolAllowlist"] = tuple(body.toolAllowlist)
    if body.toolDenylist is not None:
        container.runtime_config["toolDenylist"] = tuple(body.toolDenylist)
    if body.maxToolCallsPerRun is not None:
        container.runtime_config["maxToolCallsPerRun"] = body.maxToolCallsPerRun
    if body.maxSameToolRepeat is not None:
        container.runtime_config["maxSameToolRepeat"] = body.maxSameToolRepeat
    if body.maxToolCallsPerMinute is not None:
        container.runtime_config["maxToolCallsPerMinute"] = body.maxToolCallsPerMinute
    if body.modelRegistry is not None:
        container.runtime_config["modelRegistry"] = tuple(body.modelRegistry)
    if body.mcpServers is not None:
        container.runtime_config["mcpServers"] = tuple(body.mcpServers)
    if body.skillsEnabled is not None:
        container.runtime_config["skillsEnabled"] = tuple(body.skillsEnabled)
    if body.memory is not None:
        current_memory = container.runtime_config.get("memory", {})
        if not isinstance(current_memory, dict):
            current_memory = {}
        current_memory.update(body.memory.model_dump(exclude_none=True))
        container.runtime_config["memory"] = current_memory

    _apply_tool_policy_runtime(container)
    _apply_model_runtime(container)
    _apply_mcp_runtime(container)
    _apply_memory_runtime(container)
    _apply_skills_runtime(container)
    return {"settings": _view(container).model_dump()}
