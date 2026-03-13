"""ACP runtime registry — ported from bk/src/acp/runtime/registry.ts."""
from __future__ import annotations

from typing import Any, Protocol


class AcpBackend(Protocol):
    def get_id(self) -> str: ...
    async def start_session(self, session_key: str, agent: str, **kwargs: Any) -> Any: ...
    async def close_session(self, session_key: str, **kwargs: Any) -> None: ...


_backends: dict[str, AcpBackend] = {}


def register_acp_backend(backend_id: str, backend: AcpBackend) -> None:
    _backends[backend_id] = backend


def get_acp_backend(backend_id: str) -> AcpBackend | None:
    return _backends.get(backend_id)


def list_acp_backends() -> list[str]:
    return list(_backends.keys())
