"""Utility functions for engine and model management in tests."""

from typing import Any, cast

from pyverge.core import (
    VersionEdge,
    VersioningSettings,
    VersionNode,
)
from pyverge.core.types import (
    MigrationFunc,
    VersionValue,
)
from pyverge.migration import (
    PydanticDiff,
    Registry,
)
from pyverge.providers.types import (
    ModelAdapter,
    ModelHandle,
)


def envelope_model(
    adapter: ModelAdapter,
    versioning_settings: VersioningSettings,
    model_cls: ModelHandle | dict[str, Any],
) -> VersionNode[VersionValue]:
    """Build a versionable from a model class or a JSON schema.

    A JSON schema document is materialized into a Pydantic model first; a
    model class is wrapped directly.
    """
    return cast(
        VersionNode[VersionValue],
        adapter.versionable(cast("ModelHandle", model_cls)),
    )


def meta_versionable(
    adapter: ModelAdapter,
    kind: str,
    version: str,
) -> VersionNode[VersionValue]:
    """Build a meta version: a ``(kind, version)`` pair with no concrete model."""
    return VersionNode[VersionValue](
        _model=None,
        _value=cast(VersionValue, adapter.of(version)),
        _kind=kind,
    )


def edge_from_models(  # noqa: PLR0913
    adapter: ModelAdapter,
    versioning_settings: VersioningSettings,
    source_model: ModelHandle | dict[str, Any],
    target_model: ModelHandle | dict[str, Any],
    *,
    func: MigrationFunc,
    backward_compatible: bool = False,
) -> VersionEdge[VersionValue]:
    """Build a VersionEdge from model classes or JSON schemas.

    *source_model*/*target_model* are either Pydantic model classes or JSON
    schema documents; the JSON schema is materialized into a Pydantic model by
    the adapter at runtime.
    """
    source = envelope_model(adapter, versioning_settings, source_model)
    target = envelope_model(adapter, versioning_settings, target_model)
    return VersionEdge(
        source=source,
        target=target,
        diff=PydanticDiff.from_pair(
            source=source,
            target=target,
            is_backward_compatible=backward_compatible,
        ),
        func=func,
    )


def register_models(
    adapter: ModelAdapter,
    registry: Registry[VersionValue],
    settings: VersioningSettings,
    *models: ModelHandle,
) -> None:
    for model_cls in models:
        registry.store_model(adapter.versionable(model_cls))


_Migration = tuple[tuple[type[ModelHandle], ...], MigrationFunc]
_BackwardCompatibleMigration = tuple[
    tuple[type[ModelHandle], ...],
    MigrationFunc,
    bool,
]


def _parse_migration(
    migration: _Migration | _BackwardCompatibleMigration,
) -> tuple[tuple[type[ModelHandle], ...], MigrationFunc, bool]:
    """Normalize either migration form to ``(pair, func, compatible)``."""
    match migration:
        case (pair, func):
            return pair, func, False
        case (pair, func, backward_compatible):
            return pair, func, backward_compatible
        case _:
            raise ValueError(f"Unsupported migration spec: {migration!r}")


def register_migrations(
    adapter: ModelAdapter,
    registry: Registry[VersionValue],
    *migrations: _Migration | _BackwardCompatibleMigration,
) -> None:
    """Register migrations, each optionally marked backward compatible.

    A migration is ``((source, target), func)`` or the three-element
    ``((source, target), func, backward_compatible)`` form; the latter lets
    reverse edges declare themselves as backward compatible directly in the
    parametrize data.
    """
    for migration in migrations:
        pair, func, backward_compatible = _parse_migration(migration)
        versions = [adapter.versionable(model_cls) for model_cls in pair]
        diff = adapter.diff(
            versions[0],
            versions[1],
            is_backward_compatible=backward_compatible,
        )
        registry.store_migration(VersionEdge(versions[0], versions[1], diff, func))
