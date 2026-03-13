"""Sessions package — ported from bk/src/sessions/.

Session management utilities: key parsing, ID validation, input provenance,
model/level overrides, send policy, transcript events, and labels.
"""
from .session_key_utils import (
    parse_agent_session_key,
    derive_session_chat_type,
    is_cron_session_key,
    is_subagent_session_key,
    is_acp_session_key,
    get_subagent_depth,
    resolve_thread_parent_session_key,
)
from .session_id import looks_like_session_id
from .session_label import parse_session_label
from .send_policy import resolve_send_policy
from .input_provenance import normalize_input_provenance
