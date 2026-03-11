"""Tool policy pipeline — ported from bk/src/agents/tool-policy-pipeline.ts.

Composes multiple tool policy evaluators into a single pipeline.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from .tool_policy import PolicyDecision, ToolPolicy, ToolPolicyResult, evaluate_tool_policy


@dataclass
class ToolPolicyPipelineStage:
    name: str
    policy: ToolPolicy | None = None
    evaluator: Callable[[str], ToolPolicyResult] | None = None


@dataclass
class ToolPolicyPipelineResult:
    decision: PolicyDecision = "allow"
    reason: str | None = None
    source: str | None = None
    stage: str | None = None
    all_results: list[tuple[str, ToolPolicyResult]] = field(default_factory=list)


class ToolPolicyPipeline:
    """Pipeline of policy stages evaluated in order.

    First stage to return a non-default (deny/ask) result wins.
    """

    def __init__(self):
        self._stages: list[ToolPolicyPipelineStage] = []

    def add_stage(self, stage: ToolPolicyPipelineStage) -> "ToolPolicyPipeline":
        self._stages.append(stage)
        return self

    def add_policy(self, name: str, policy: ToolPolicy) -> "ToolPolicyPipeline":
        self._stages.append(ToolPolicyPipelineStage(name=name, policy=policy))
        return self

    def evaluate(self, tool_id: str) -> ToolPolicyPipelineResult:
        all_results: list[tuple[str, ToolPolicyResult]] = []

        for stage in self._stages:
            if stage.evaluator:
                result = stage.evaluator(tool_id)
            elif stage.policy:
                result = evaluate_tool_policy(stage.policy, tool_id)
            else:
                continue

            all_results.append((stage.name, result))

            if result.decision == "deny":
                return ToolPolicyPipelineResult(
                    decision="deny",
                    reason=result.reason,
                    source=result.source,
                    stage=stage.name,
                    all_results=all_results,
                )
            if result.decision == "ask":
                return ToolPolicyPipelineResult(
                    decision="ask",
                    reason=result.reason,
                    source=result.source,
                    stage=stage.name,
                    all_results=all_results,
                )

        return ToolPolicyPipelineResult(
            decision="allow",
            all_results=all_results,
        )
