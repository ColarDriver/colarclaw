# ADR 0001: OpenClaw Core Assistant Rewrite (Python + React)

- Status: Accepted
- Date: 2026-03-09
- Scope: Core assistant web product

## Context

The historical OpenClaw runtime was TypeScript-first and multi-channel. We now need:

1. A fully separated frontend and backend architecture.
2. A Python backend built around FastAPI + LangChain + LangGraph.
3. A React frontend (Node.js toolchain), web-only.
4. A Big Bang cutover while preserving core assistant behavior.

## Decision

- Move legacy TypeScript `src/` into `bk/src/` for rollback and reference.
- Rebuild active runtime in Python under `src`.
- Define stable v1 API and WebSocket contracts in `contracts/`.
- Build a React control web app in `ui/src/`.
- Execute migration with scripted validation and runbooks.

## Consequences

- Existing TypeScript runtime becomes a backup reference and migration source.
- New backend is service-oriented and easier to operate independently.
- Frontend stack is consolidated to React and no longer depends on native shells.
- Big Bang cutover risk is mitigated by quality gates and rollback scripts.
