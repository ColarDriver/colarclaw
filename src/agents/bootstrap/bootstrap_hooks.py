"""Bootstrap hooks — ported from bk/src/agents/bootstrap-hooks.ts.

Applies internal hook overrides to bootstrap files before injection.
"""
from __future__ import annotations

from typing import Any


async def apply_bootstrap_hook_overrides(
    files: list[Any],
    workspace_dir: str,
    config: Any | None = None,
    session_key: str | None = None,
    session_id: str | None = None,
    agent_id: str | None = None,
) -> list[Any]:
    """Apply bootstrap hook overrides.

    Triggers the ``agent:bootstrap`` internal hook and returns the
    (potentially modified) bootstrap files list.
    """
    resolved_session_key = session_key or session_id or "unknown"
    # Resolve agent id from session_key if not provided
    resolved_agent_id = agent_id
    if resolved_agent_id is None and session_key:
        try:
            from ..routing.session_key import resolve_agent_id_from_session_key
            resolved_agent_id = resolve_agent_id_from_session_key(session_key)
        except (ImportError, Exception):
            pass

    context = {
        "workspace_dir": workspace_dir,
        "bootstrap_files": files,
        "cfg": config,
        "session_key": session_key,
        "session_id": session_id,
        "agent_id": resolved_agent_id,
    }

    try:
        from ..hooks.internal_hooks import create_internal_hook_event, trigger_internal_hook

        event = create_internal_hook_event("agent", "bootstrap", resolved_session_key, context)
        await trigger_internal_hook(event)
        updated = event.get("context", {}).get("bootstrap_files")
        return updated if isinstance(updated, list) else files
    except (ImportError, Exception):
        return files
