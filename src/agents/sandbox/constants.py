"""Sandbox constants — ported from bk/src/agents/sandbox/constants.ts."""
from __future__ import annotations

DEFAULT_SANDBOX_IMAGE = "ghcr.io/openclaw/sandbox:latest"
DEFAULT_SANDBOX_COMMON_IMAGE = "ghcr.io/openclaw/sandbox-common:latest"
DEFAULT_SANDBOX_BROWSER_IMAGE = "ghcr.io/openclaw/sandbox-browser:latest"

SANDBOX_CONTAINER_WORKDIR = "/workspace"
SANDBOX_LABEL_PREFIX = "ai.openclaw.sandbox"
SANDBOX_SESSION_LABEL = f"{SANDBOX_LABEL_PREFIX}.session"
SANDBOX_AGENT_LABEL = f"{SANDBOX_LABEL_PREFIX}.agent"
