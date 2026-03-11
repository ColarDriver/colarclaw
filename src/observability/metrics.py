from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field


@dataclass
class InMemoryMetrics:
    counters: Counter[str] = field(default_factory=Counter)

    def inc(self, key: str, amount: int = 1) -> None:
        self.counters[key] += amount

    def snapshot(self) -> dict[str, int]:
        return dict(self.counters)
