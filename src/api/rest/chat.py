"""Chat REST API – REST runs + real-streaming endpoint.

Upgraded from the stub: the /runs/stream endpoint now uses
GraphOrchestrator.stream() which calls the real LLM provider's
streaming API, yielding tokens as they arrive.

Session message history is fetched and injected into the LLM context
before each run so the model has multi-turn memory.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..deps import get_auth_context, get_container
from ...schemas.chat import ChatRunRequest, ChatRunResponse, RetrievedContextItem

router = APIRouter(prefix="/v1/chat", tags=["chat"])


def _encode_ndjson(payload: dict[str, object]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


def _validate_requested_model(container, model: str | None) -> None:
    if model is None:
        return
    # If registry has explicit entries, validate against it
    if container.model_registry.keys() and not container.model_registry.has(model):
        raise HTTPException(status_code=400, detail=f"model not registered: {model}")


async def _load_session_messages(container, session_id: str) -> list[dict]:
    """Load recent session messages for multi-turn context injection."""
    try:
        async with container.session_factory() as db:
            from sqlalchemy import select
            from session.models import MessageModel, SessionModel

            result = await db.execute(
                select(MessageModel)
                .where(MessageModel.session_id == session_id)
                .order_by(MessageModel.created_at_ms.asc())
                .limit(40)  # last 40 messages = ~20 turns
            )
            rows = result.scalars().all()
            return [{"role": row.role, "content": row.text} for row in rows]
    except Exception:
        return []


@router.post("/runs")
async def run_chat(
    body: ChatRunRequest,
    container=Depends(get_container),
    _auth=Depends(get_auth_context),
) -> dict[str, object]:
    _validate_requested_model(container, body.model)
    lock = container.session_runtime.lock_for_session(body.sessionId)
    async with lock:
        existing_run_id = container.session_runtime.find_run_by_idempotency(
            session_id=body.sessionId,
            idempotency_key=body.idempotencyKey,
        )
        if existing_run_id:
            return {
                "run": ChatRunResponse(
                    runId=existing_run_id,
                    sessionId=body.sessionId,
                    text="(deduplicated request, no re-execution)",
                    tools=[],
                    retrievedContext=[],
                    deduplicated=True,
                ).model_dump()
            }

        run_id = f"run_{uuid.uuid4().hex}"
        container.session_runtime.start_run(
            run_id=run_id,
            session_id=body.sessionId,
            idempotency_key=body.idempotencyKey,
        )

        try:
            session_messages = await _load_session_messages(container, body.sessionId)
            state = await container.graph.run(
                run_id=run_id,
                session_id=body.sessionId,
                message=body.message,
                model=body.model,
                session_messages=session_messages,
            )
            payload = ChatRunResponse(
                runId=run_id,
                sessionId=body.sessionId,
                text=state.response_text,
                tools=[
                    {"name": item.name, "args": item.args, "result": item.result}
                    for item in state.tool_events
                ],
                retrievedContext=[
                    RetrievedContextItem(
                        path=item.path,
                        startLine=item.start_line,
                        endLine=item.end_line,
                        score=item.score,
                        snippet=item.snippet,
                        source=item.source,
                        citation=item.citation,
                    )
                    for item in state.retrieved_context
                ],
            )
            container.session_runtime.finish_run(run_id, status="completed")
            container.tool_runtime.reset_run_state(run_id)
            return {"run": payload.model_dump()}
        except Exception:
            container.session_runtime.finish_run(run_id, status="failed")
            container.tool_runtime.reset_run_state(run_id)
            raise


@router.post("/runs/{run_id}/abort")
async def abort_chat_run(
    run_id: str,
    container=Depends(get_container),
    _auth=Depends(get_auth_context),
) -> dict[str, object]:
    aborted = container.session_runtime.abort_run(run_id)
    if not aborted:
        raise HTTPException(status_code=404, detail="run not found")
    container.tool_runtime.reset_run_state(run_id)
    return {"run": {"runId": run_id, "status": "aborted"}}


@router.post("/runs/stream")
async def run_chat_stream(
    body: ChatRunRequest,
    container=Depends(get_container),
    _auth=Depends(get_auth_context),
) -> StreamingResponse:
    _validate_requested_model(container, body.model)
    run_id = f"run_{uuid.uuid4().hex}"

    async def gen() -> AsyncIterator[bytes]:
        lock = container.session_runtime.lock_for_session(body.sessionId)
        async with lock:
            existing_run_id = container.session_runtime.find_run_by_idempotency(
                session_id=body.sessionId,
                idempotency_key=body.idempotencyKey,
            )
            if existing_run_id:
                yield _encode_ndjson(
                    {
                        "type": "final",
                        "runId": existing_run_id,
                        "sessionId": body.sessionId,
                        "text": "(deduplicated request, no re-execution)",
                        "deduplicated": True,
                    }
                )
                return

            container.session_runtime.start_run(
                run_id=run_id,
                session_id=body.sessionId,
                idempotency_key=body.idempotencyKey,
            )

            try:
                yield _encode_ndjson(
                    {
                        "type": "lifecycle",
                        "phase": "start",
                        "runId": run_id,
                        "sessionId": body.sessionId,
                    }
                )

                session_messages = await _load_session_messages(container, body.sessionId)

                # Use real streaming from the graph/LLM
                aggregate = ""
                stream_gen = await container.graph.stream(
                    run_id=run_id,
                    session_id=body.sessionId,
                    message=body.message,
                    model=body.model,
                    session_messages=session_messages,
                )
                async for token in stream_gen:
                    aggregate += token
                    yield _encode_ndjson(
                        {
                            "type": "delta",
                            "runId": run_id,
                            "sessionId": body.sessionId,
                            "delta": token,
                            "text": aggregate,
                        }
                    )

                yield _encode_ndjson(
                    {
                        "type": "final",
                        "runId": run_id,
                        "sessionId": body.sessionId,
                        "text": aggregate,
                    }
                )
                yield _encode_ndjson(
                    {
                        "type": "lifecycle",
                        "phase": "end",
                        "runId": run_id,
                        "sessionId": body.sessionId,
                    }
                )
                container.session_runtime.finish_run(run_id, status="completed")
                container.tool_runtime.reset_run_state(run_id)

            except Exception as err:
                container.session_runtime.finish_run(run_id, status="failed")
                container.tool_runtime.reset_run_state(run_id)
                yield _encode_ndjson(
                    {
                        "type": "error",
                        "runId": run_id,
                        "sessionId": body.sessionId,
                        "message": str(err),
                    }
                )

    return StreamingResponse(gen(), media_type="application/x-ndjson")
