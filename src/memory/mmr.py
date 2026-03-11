from __future__ import annotations

from dataclasses import dataclass
import math
import re


@dataclass(frozen=True)
class MmrConfig:
    enabled: bool = False
    lambda_value: float = 0.7


_token_pattern = re.compile(r"[\w]+", flags=re.UNICODE)


def _tokenize(value: str) -> set[str]:
    return {token.lower() for token in _token_pattern.findall(value)}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def apply_mmr_to_results(results: list[dict[str, object]], config: MmrConfig) -> list[dict[str, object]]:
    if not config.enabled or len(results) <= 2:
        return results

    lambda_value = max(0.0, min(1.0, config.lambda_value))
    candidates = [dict(item) for item in results]
    token_cache = [_tokenize(str(item.get('snippet', ''))) for item in candidates]

    selected: list[dict[str, object]] = []
    selected_tokens: list[set[str]] = []

    while candidates:
        best_index = 0
        best_score = -math.inf
        for idx, candidate in enumerate(candidates):
            base_score = float(candidate.get('score', 0.0))
            candidate_tokens = token_cache[idx]
            novelty_penalty = 0.0
            if selected_tokens:
                novelty_penalty = max(_jaccard(candidate_tokens, prior) for prior in selected_tokens)
            score = (lambda_value * base_score) - ((1.0 - lambda_value) * novelty_penalty)
            if score > best_score:
                best_score = score
                best_index = idx

        selected.append(candidates.pop(best_index))
        selected_tokens.append(token_cache.pop(best_index))

    return selected
