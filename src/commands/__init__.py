"""CLI command handlers.

Ported from bk/src/commands/ (~216 TS files).

Organized into sub-modules:
- agent: Agent run command
- config_cmd: Config get/set/edit commands
- send: Message sending command
- gateway: Gateway start/stop/status
- channels: Channel management commands
- status: System status display
- sessions: Session management
- onboard: Interactive onboarding/setup wizard
- auth: Authentication configuration
- doctor: Diagnostics/troubleshooting
- registry: Command registry and routing
"""

from .registry import CommandRegistry, CommandDef

__all__ = [
    "CommandRegistry",
    "CommandDef",
]
