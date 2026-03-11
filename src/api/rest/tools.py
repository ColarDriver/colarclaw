from __future__ import annotations

from fastapi import APIRouter, Depends

from api.deps import get_auth_context, get_container

router = APIRouter(prefix="/v1/tools", tags=["tools"])


@router.get("")
async def list_tools(container=Depends(get_container), _auth=Depends(get_auth_context)) -> dict[str, object]:
    tools = [
        {"name": tool.name, "description": tool.description}
        for tool in container.tool_registry.list()
    ]
    return {"tools": tools}
