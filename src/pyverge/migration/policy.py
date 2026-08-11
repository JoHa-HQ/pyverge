"""Target resolver factories for migration graphs.

The migration engine is deliberately agnostic about *what* target version each
payload entry should converge to. This module provides lightweight
:class:`~pyverge.migration.types.TargetResolver` factories that
:class:`GraphBuilder` and the individual :class:`EntryMigration` strategies
consume.

Declarative spec compilation lives in :mod:`~pyverge.migration.manager`, the
high-level facade that turns strings, model classes, and per-kind mappings into
resolved resolvers before invoking the engine.
"""

from __future__ import annotations

from typing import Literal

from .exceptions import RegistryError
from .registry import Registry
from .types import (
    ModelBase,
    ModelKind,
    TargetResolver,
    Versionable,
    VersionValue,
    VersionValue_co,
    VModel_co,
)


def skip_target_resolver(
    registry: Registry[VersionValue, ModelBase],
) -> TargetResolver:
    """Return a resolver that always skips (returns ``None``).

    *registry* is accepted to keep the factory signature uniform with
    ``latest_target_resolver`` and ``earliest_target_resolver``; it is not
    used by the returned resolver.
    """

    def resolve(
        current: Versionable[VersionValue_co, VModel_co],
    ) -> Versionable[VersionValue_co, VModel_co] | None:
        return None

    return resolve


def latest_target_resolver(
    registry: Registry[VersionValue, ModelBase],
) -> TargetResolver:
    """Return a resolver that converges to the latest registered version per kind."""

    def resolve(
        current: Versionable[VersionValue_co, VModel_co],
    ) -> Versionable[VersionValue_co, VModel_co] | None:
        return registry.latest(current.kind)

    return resolve


def earliest_target_resolver(
    registry: Registry[VersionValue, ModelBase],
) -> TargetResolver:
    """Return a resolver that converges to the earliest registered version per kind."""

    def resolve(
        current: Versionable[VersionValue_co, VModel_co],
    ) -> Versionable[VersionValue_co, VModel_co] | None:
        return registry.earliest(current.kind)

    return resolve


def fixed_target_resolver(
    registry: Registry[VersionValue, ModelBase],
    target: Versionable[VersionValue, ModelBase],
) -> TargetResolver:
    """Return a resolver that always returns *target* for its kind.

    The *target* is validated against *registry* immediately; a missing
    target raises :class:`RegistryError` with source ``"target"``.
    """
    if not registry.has_model(target):
        raise RegistryError(
            registry.name,
            f"Target {target} is not registered",
        )

    def resolve(
        current: Versionable[VersionValue_co, VModel_co],
    ) -> Versionable[VersionValue_co, VModel_co] | None:
        if current.kind != target.kind:
            raise RegistryError(
                registry.name,
                f"Target {target} belongs to kind {target.kind!r}, "
                f"but entry kind is {current.kind!r}",
            )
        return target

    return resolve


def multi_target_resolver(
    resolvers: dict[ModelKind | Literal["*"], TargetResolver],
) -> TargetResolver:
    """Compose per-kind resolvers into a single dispatcher.

    The special key ``"*"`` is used as the fallback for kinds not explicitly
    listed. The input mapping is read but not modified.
    """
    fallback = resolvers.get("*")
    by_kind: dict[ModelKind, TargetResolver] = {
        k: v for k, v in resolvers.items() if k != "*"
    }

    def resolve(
        current: Versionable[VersionValue_co, VModel_co],
    ) -> Versionable[VersionValue_co, VModel_co] | None:
        resolver = by_kind.get(current.kind, fallback)
        if resolver is None:
            return None
        return resolver(current)

    return resolve
