"""Models package."""
from .catalog import (
    ModelCatalogEntry,
    ModelInputType,
    find_model_in_catalog,
    load_model_catalog,
    model_supports_document,
    model_supports_vision,
    reset_model_catalog_cache,
)
from .compat import (
    ModelCompat,
    ModelSpec,
    normalize_model_compat,
)
from .registry import (
    ModelRef,
    ModelRegistry,
    RegisteredModel,
    parse_model_ref,
    parse_registered_model_entries,
)

__all__ = [
    "ModelCatalogEntry",
    "ModelInputType",
    "find_model_in_catalog",
    "load_model_catalog",
    "model_supports_document",
    "model_supports_vision",
    "reset_model_catalog_cache",
    "ModelCompat",
    "ModelSpec",
    "normalize_model_compat",
    "ModelRef",
    "ModelRegistry",
    "RegisteredModel",
    "parse_model_ref",
    "parse_registered_model_entries",
]
