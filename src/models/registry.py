from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRef:
    provider: str
    model: str

    @property
    def key(self) -> str:
        return f"{self.provider}/{self.model}"


@dataclass(frozen=True)
class RegisteredModel:
    provider: str
    id: str
    name: str
    reasoning: bool = False
    context_window: int | None = None

    @property
    def key(self) -> str:
        return f"{self.provider}/{self.id}"


def parse_model_ref(raw: str, default_provider: str = "openai") -> ModelRef | None:
    value = raw.strip()
    if not value:
        return None
    if "/" not in value:
        return ModelRef(provider=default_provider, model=value)
    provider_raw, model_raw = value.split("/", 1)
    provider = provider_raw.strip().lower()
    model = model_raw.strip()
    if not provider or not model:
        return None
    return ModelRef(provider=provider, model=model)


class ModelRegistry:
    def __init__(self, models: list[RegisteredModel] | None = None) -> None:
        self._models: dict[str, RegisteredModel] = {}
        if models:
            self.replace(models)

    def replace(self, models: list[RegisteredModel]) -> None:
        next_models: dict[str, RegisteredModel] = {}
        for item in models:
            key = item.key
            next_models[key] = RegisteredModel(
                provider=item.provider.strip().lower(),
                id=item.id.strip(),
                name=item.name.strip() or item.id.strip(),
                reasoning=bool(item.reasoning),
                context_window=item.context_window,
            )
        self._models = next_models

    def list(self) -> list[RegisteredModel]:
        return sorted(self._models.values(), key=lambda item: item.key)

    def keys(self) -> set[str]:
        return set(self._models.keys())

    def has(self, model_key: str) -> bool:
        return model_key in self._models


def parse_registered_model_entries(raw_entries: tuple[str, ...]) -> list[RegisteredModel]:
    parsed: list[RegisteredModel] = []
    for raw in raw_entries:
        value = raw.strip()
        if not value:
            continue
        label = ""
        if "=" in value:
            left, right = value.split("=", 1)
            value = left.strip()
            label = right.strip()
        ref = parse_model_ref(value)
        if ref is None:
            continue
        parsed.append(
            RegisteredModel(
                provider=ref.provider,
                id=ref.model,
                name=label or ref.model,
            )
        )
    return parsed
