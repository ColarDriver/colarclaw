from __future__ import annotations

import asyncio
import json
import uuid

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from core.auth import resolve_websocket_auth
from core.config import load_settings

router = APIRouter(tags=["ws"])


def _validate_requested_model(container, model: object) -> str | None:
    if model is None:
        return None
    if not isinstance(model, str):
        raise HTTPException(status_code=400, detail="model must be string")
    value = model.strip()
    if not value:
        return None
    if not container.model_registry.has(value):
        raise HTTPException(status_code=400, detail=f"model not registered: {value}")
    return value


@router.websocket("/v1/ws/chat")
async def chat_socket(websocket: WebSocket) -> None:
    settings = load_settings()
    try:
        auth = resolve_websocket_auth(websocket, settings)
    except HTTPException:
        await websocket.close(code=4401, reason="unauthorized")
        return

    await websocket.accept()
    container = websocket.app.state.container
    connected_at = int(asyncio.get_event_loop().time() * 1000)

    await websocket.send_json(
        {
            "type": "event",
            "event": "connect.ok",
            "payload": {
                "subject": auth.subject,
                "scopes": list(auth.scopes),
                "connectedAtMs": connected_at,
                "features": ["chat.send", "chat.abort", "ping"],
            },
        }
    )

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                frame = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "invalid json"})
                continue

            frame_type = str(frame.get("type", ""))
            if frame_type == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if frame_type == "chat.abort":
                run_id = str(frame.get("runId", "")).strip()
                if not run_id:
                    await websocket.send_json({"type": "error", "message": "runId is required for chat.abort"})
                    continue
                aborted = container.session_runtime.abort_run(run_id)
                await websocket.send_json(
                    {
                        "type": "lifecycle",
                        "phase": "aborted" if aborted else "noop",
                        "runId": run_id,
                    }
                )
                continue

            if frame_type != "chat.send":
                await websocket.send_json({"type": "error", "message": "unsupported frame type"})
                continue

            session_id = str(frame.get("sessionId", "main"))
            message = str(frame.get("message", "")).strip()
            try:
                model = _validate_requested_model(container, frame.get("model"))
            except HTTPException as exc:
                await websocket.send_json({"type": "error", "message": str(exc.detail)})
                continue
            idempotency_key = frame.get("idempotencyKey")
            idempotency_key = str(idempotency_key).strip() if isinstance(idempotency_key, str) else None

            if not message:
                await websocket.send_json({"type": "error", "message": "message is required"})
                continue

            lock = container.session_runtime.lock_for_session(session_id)
            async with lock:
                dedup_run_id = container.session_runtime.find_run_by_idempotency(
                    session_id=session_id,
                    idempotency_key=idempotency_key,
                )
                if dedup_run_id:
                    await websocket.send_json(
                        {
                            "type": "final",
                            "runId": dedup_run_id,
                            "sessionId": session_id,
                            "text": "(deduplicated request, no re-execution)",
                            "deduplicated": True,
                        }
                    )
                    continue

                run_id = f"run_{uuid.uuid4().hex}"
                container.session_runtime.start_run(
                    run_id=run_id,
                    session_id=session_id,
                    idempotency_key=idempotency_key,
                )

                await websocket.send_json(
                    {
                        "type": "lifecycle",
                        "phase": "start",
                        "runId": run_id,
                        "sessionId": session_id,
                    }
                )

                try:
                    state = await container.graph.run(
                        run_id=run_id,
                        session_id=session_id,
                        message=message,
                        model=model,
                    )

                    text = state.response_text
                    aggregate = ""
                    for idx in range(0, len(text), 16):
                        chunk = text[idx : idx + 16]
                        aggregate += chunk
                        await websocket.send_json(
                            {
                                "type": "delta",
                                "runId": run_id,
                                "sessionId": session_id,
                                "delta": chunk,
                                "text": aggregate,
                            }
                        )
                        await asyncio.sleep(0.01)

                    for tool in state.tool_events:
                        await websocket.send_json(
                            {
                                "type": "tool_end",
                                "runId": run_id,
                                "sessionId": session_id,
                                "name": tool.name,
                                "args": tool.args,
                                "result": tool.result,
                            }
                        )

                    await websocket.send_json(
                        {
                            "type": "final",
                            "runId": run_id,
                            "sessionId": session_id,
                            "text": text,
                        }
                    )
                    await websocket.send_json(
                        {
                            "type": "lifecycle",
                            "phase": "end",
                            "runId": run_id,
                            "sessionId": session_id,
                        }
                    )
                    container.session_runtime.finish_run(run_id, status="completed")
                    container.tool_runtime.reset_run_state(run_id)
                except Exception as err:
                    container.session_runtime.finish_run(run_id, status="failed")
                    container.tool_runtime.reset_run_state(run_id)
                    await websocket.send_json(
                        {
                            "type": "error",
                            "runId": run_id,
                            "sessionId": session_id,
                            "message": str(err),
                        }
                    )
    except WebSocketDisconnect:
        return
