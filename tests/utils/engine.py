# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

"""Utility functions for engine and model management in tests."""

from __future__ import annotations

from typing import Any, cast

from pyverge.core import MigrationFunc, VersionValue
from pyverge.migrations.identity import DefaultMigrationIdentityResolver
from pyverge.registry import Registry
from pyverge.schemas.types import (
    ModelAdapter,
    ModelHandle,
)
from pyverge.settings import VersioningSettings
from pyverge.versioning import Diff, VersionEdge, VersionKey, VersionNode


def envelope_model(
    adapter: ModelAdapter,
    versioning_settings: VersioningSettings | None,
    model_cls: ModelHandle | dict[str, Any],
) -> VersionNode[VersionValue]:
    """Build a versionable from a model class or a JSON schema.

    A JSON schema document is materialized into a Pydantic model first; a
    model class is wrapped directly.
    """
    return adapter.versionable(cast("ModelHandle", model_cls))


def meta_versionable(
    adapter: ModelAdapter,
    kind: str,
    version: str,
) -> VersionKey[VersionValue]:
    """Build a temporary search key for a ``(kind, version)`` pair."""
    return VersionKey[VersionValue](
        _value=cast(VersionValue, adapter.of(version)),
        _kind=kind,
    )


def edge_from_nodes(
    adapter: ModelAdapter,
    source: VersionNode,
    target: VersionNode,
    *,
    func: MigrationFunc,
) -> VersionEdge[VersionValue]:
    """Build a VersionEdge from two materialized version nodes."""
    return VersionEdge(
        source=source,
        target=target,
        diff=Diff.from_pair(source=source, target=target, adapter=adapter),
        func=func,
        migration=DefaultMigrationIdentityResolver().resolve(func),
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
    """Build a VersionEdge from model classes or JSON schemas."""
    return edge_from_nodes(
        adapter,
        envelope_model(adapter, versioning_settings, source_model),
        envelope_model(adapter, versioning_settings, target_model),
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
    """Register migration definitions in a registry."""
    for pair, func, backward_compatible in (
        _parse_migration(migration) for migration in migrations
    ):
        registry.store_migration(pair, func, backward_compatible=backward_compatible)
