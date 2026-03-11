from __future__ import annotations

import logging
from typing import Any


class AuditLogger:
    def __init__(self) -> None:
        self._logger = logging.getLogger("openclaw.audit")

    def tool_call(self, *, run_id: str, tool_name: str, args: dict[str, Any], result: str) -> None:
        self._logger.info(
            "tool_call run_id=%s tool=%s args=%s result=%s",
            run_id,
            tool_name,
            args,
            result,
        )
