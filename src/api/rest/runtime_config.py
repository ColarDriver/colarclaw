from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_auth_context, get_container
from mcp.registry import parse_mcp_servers
from models.registry import parse_registered_model_entries
from schemas.runtime_config import (
    McpServerItem,
    ModelItem,
    RuntimeConfigView,
    SkillItem,
    UpdateRuntimeConfigRequest,
)

router = APIRouter(prefix="/v1/runtime", tags=["runtime"])


def _view(container) -> RuntimeConfigView:
    return RuntimeConfigView(
        modelRegistry=[
            ModelItem(
                key=item.key,
                provider=item.provider,
                id=item.id,
                name=item.name,
                reasoning=item.reasoning,
                contextWindow=item.context_window,
            )
            for item in container.model_registry.list()
        ],
        mcpServers=[
            McpServerItem(name=item.name, command=item.command, enabled=item.enabled)
            for item in container.mcp_registry.list()
        ],
        skillsEnabled=list(container.runtime_config.get("skillsEnabled", ())),
        skillsAvailable=[
            SkillItem(key=item.key, name=item.name, description=item.description)
            for item in container.skill_catalog.list()
        ],
        memory=dict(container.runtime_config.get("memory", {})),
    )


@router.get("")
async def get_runtime(container=Depends(get_container), _auth=Depends(get_auth_context)) -> dict[str, object]:
    return {"runtime": _view(container).model_dump()}


@router.put("")
async def put_runtime(
    body: UpdateRuntimeConfigRequest,
    container=Depends(get_container),
    _auth=Depends(get_auth_context),
) -> dict[str, object]:
    if body.modelRegistry is not None:
        model_entries = tuple(item.strip() for item in body.modelRegistry if item.strip())
        container.runtime_config["modelRegistry"] = model_entries
        container.model_registry.replace(parse_registered_model_entries(model_entries))

    if body.mcpServers is not None:
        mcp_entries = tuple(item.strip() for item in body.mcpServers if item.strip())
        container.runtime_config["mcpServers"] = mcp_entries
        container.mcp_registry.replace(parse_mcp_servers(mcp_entries))

    if body.skillsEnabled is not None:
        skills_enabled = tuple(item.strip() for item in body.skillsEnabled if item.strip())
        container.runtime_config["skillsEnabled"] = skills_enabled
        container.graph.update_skills_enabled(skills_enabled)

    if body.memory is not None:
        current_memory = container.runtime_config.get("memory", {})
        if not isinstance(current_memory, dict):
            current_memory = {}
        current_memory.update(body.memory)
        container.runtime_config["memory"] = current_memory

    container.skill_catalog.reload()
    return {"runtime": _view(container).model_dump()}
