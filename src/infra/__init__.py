"""Infra module — infrastructure utilities for the colarclaw gateway.

Organized into functional subpackages:
- exec:      Execution safety, approvals, system-run commands
- device:    Device identity, pairing, Bonjour/mDNS
- network:   Networking, ports, SSH, TLS, Tailscale
- gateway:   Gateway lifecycle, channels, restart, outbound
- update:    Update checking, install flows
- session:   Session cost tracking, provider usage
- heartbeat: Heartbeat runner and visibility
- fs:        File operations, boundary checks, state, git
- process:   Process management, shell environment
- platform:  Platform detection, config, security, doctor
- events:    Event system, diagnostics
- util:      Formatting, dedup, retry, miscellaneous helpers
"""
from __future__ import annotations

# Re-export commonly used items for convenience
from .errors import extract_error_code, format_error_message, format_uncaught_error
from .env import is_truthy_env_value, normalize_env, load_dotenv
