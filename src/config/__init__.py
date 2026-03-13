"""OpenClaw configuration system.

Ported from bk/src/config/ (~133 TS files, ~26k lines).

Organized into sub-modules:
- types: Configuration type definitions and dataclasses
- paths: Config file path resolution and state directory
- io: Config file loading, parsing, writing, caching
- defaults: Default value application for models, agents, sessions, etc.
- env: Environment variable handling, substitution, dotenv
- validation: Schema validation and issue reporting
- schema: Zod-like schema definitions
- store: Session store and cache management
- merge: Config merge/patch operations
- legacy: Legacy config migration
- security: Redaction, prototype key blocking
"""

from .types import OpenClawConfig
from .paths import (
    resolve_config_path,
    resolve_state_dir,
    resolve_default_config_candidates,
)
from .io import (
    load_config,
    create_config_io,
    parse_config_json5,
    write_config_file,
    clear_config_cache,
)
from .defaults import (
    apply_model_defaults,
    apply_agent_defaults,
    apply_session_defaults,
    apply_logging_defaults,
    apply_message_defaults,
    apply_compaction_defaults,
    apply_context_pruning_defaults,
)
from .validation import validate_config_object
from .env import apply_config_env_vars, resolve_config_env_vars

__all__ = [
    "OpenClawConfig",
    "resolve_config_path",
    "resolve_state_dir",
    "resolve_default_config_candidates",
    "load_config",
    "create_config_io",
    "parse_config_json5",
    "write_config_file",
    "clear_config_cache",
    "apply_model_defaults",
    "apply_agent_defaults",
    "apply_session_defaults",
    "apply_logging_defaults",
    "apply_message_defaults",
    "apply_compaction_defaults",
    "apply_context_pruning_defaults",
    "validate_config_object",
    "apply_config_env_vars",
    "resolve_config_env_vars",
]
