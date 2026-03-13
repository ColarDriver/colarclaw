"""Shared package — ported from bk/src/shared/.

Cross-cutting utilities shared across modules: string normalization,
config evaluation, requirements checking, IP address handling,
text processing, usage metrics, and more.
"""
from .string_normalization import (
    normalize_string_entries,
    normalize_string_entries_lower,
    normalize_hyphen_slug,
    normalize_at_hash_slug,
)
from .config_eval import (
    is_truthy,
    resolve_config_path,
    has_binary,
    evaluate_runtime_requires,
)
from .text_processing import (
    strip_reasoning_tags_from_text,
    truncate_line,
    format_duration_compact,
    format_token_short,
)
