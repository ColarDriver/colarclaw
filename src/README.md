# OpenClaw Python Backend (uv workflow)

## Setup with uv

```bash
python3 -m uv venv .venv
python3 -m uv pip install --python .venv/bin/python -r requirements.backend.txt
```

## Run

```bash
python3 -m uv run --python .venv/bin/python python main.py
```

## Test

```bash
PYTHONPATH=src python3 -m uv run --python .venv/bin/python pytest tests/backend -q
```

## API

- `GET /healthz`
- `GET /v1/sessions`
- `POST /v1/sessions`
- `GET /v1/sessions/{session_id}`
- `POST /v1/chat/runs`
- `POST /v1/chat/runs/{run_id}/abort`
- `POST /v1/chat/runs/stream`
- `GET /v1/tools`
- `GET/PUT /v1/settings`
- `GET/PUT /v1/runtime`
- `WS /v1/ws/chat` (Bearer token in header or `?token=`)

## Web gateway notes

- WebSocket supports `chat.send`, `chat.abort`, and `ping`.
- Session runtime adds per-session lock + idempotency key dedup.
- Tool policy enforces allow/deny, per-run limits, and anti-loop guards.
- Model registry controls selectable `provider/model` keys.
- Skills are discovered from `skills/**/SKILL.md` (plus extension skills) and can be enabled per runtime settings.
