from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_auth_context, get_container
from schemas.sessions import CreateSessionRequest, MessageView, SessionDetailView, SessionView

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


@router.get("")
async def list_sessions(container=Depends(get_container), _auth=Depends(get_auth_context)) -> dict[str, object]:
    sessions = await container.session_repo.list_sessions()
    payload = [
        SessionView(id=item.id, title=item.title, createdAtMs=item.created_at_ms, updatedAtMs=item.updated_at_ms).model_dump()
        for item in sessions
    ]
    return {"sessions": payload}


@router.post("")
async def create_session(
    body: CreateSessionRequest,
    container=Depends(get_container),
    _auth=Depends(get_auth_context),
) -> dict[str, object]:
    created = await container.session_repo.create_session(body.title)
    return {
        "session": SessionView(
            id=created.id,
            title=created.title,
            createdAtMs=created.created_at_ms,
            updatedAtMs=created.updated_at_ms,
        ).model_dump()
    }


@router.get("/{session_id}")
async def get_session(
    session_id: str,
    container=Depends(get_container),
    _auth=Depends(get_auth_context),
) -> dict[str, object]:
    session = await container.session_repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="session not found")
    messages = await container.session_repo.list_messages(session_id)
    detail = SessionDetailView(
        id=session.id,
        title=session.title,
        createdAtMs=session.created_at_ms,
        updatedAtMs=session.updated_at_ms,
        messages=[
            MessageView(
                id=msg.id,
                sessionId=msg.session_id,
                role=msg.role,
                text=msg.text,
                createdAtMs=msg.created_at_ms,
            )
            for msg in messages
        ],
    )
    return {"session": detail.model_dump()}
