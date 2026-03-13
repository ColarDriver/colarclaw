"""Routing package — ported from bk/src/routing/.

Message routing engine: agent selection, session key construction,
account management, and binding resolution.

Modules:
    account_id           — account ID normalization
    account_lookup       — account entry resolution
    session_key          — session key construction and parsing
    bindings             — binding listing and account lookup
    resolve_route        — full agent route resolution engine
    default_account_warnings — config path formatting helpers
"""
from .account_id import DEFAULT_ACCOUNT_ID, normalize_account_id
from .session_key import (
    DEFAULT_AGENT_ID,
    normalize_agent_id,
    build_agent_main_session_key,
    build_agent_peer_session_key,
)
from .resolve_route import resolve_agent_route, ResolvedAgentRoute
