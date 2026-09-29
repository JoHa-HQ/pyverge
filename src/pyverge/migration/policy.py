"""Target resolver factories for migration graphs.

The engine is agnostic about *what* version each entry converges to; these
factories produce the :class:`TargetResolver` it consumes. Declarative spec
compilation lives in :mod:`~pyverge.manager`.
"""

from __future__ import annotations

from typing import Literal

from pyverge.core.exceptions import RegistryError
from pyverge.types import (
    ModelBase,
    ModelKind,
    TargetResolver,
    Versionable,
    VersionValue,
    VersionValue_co,
    VModel_co,
)

from .registry import Registry


def skip_target_resolver(
    registry: Registry[VersionValue, ModelBase],
) -> TargetResolver:
    """A resolver that always skips (returns ``None``)."""

    def resolve(
        current: Versionable[VersionValue_co, VModel_co],
    ) -> Versionable[VersionValue_co, VModel_co] | None:
        return None

    return resolve


def latest_target_resolver(
    registry: Registry[VersionValue, ModelBase],
) -> TargetResolver:
    """A resolver that converges to the latest registered version per kind."""

    def resolve(
        current: Versionable[VersionValue_co, VModel_co],
    ) -> Versionable[VersionValue_co, VModel_co] | None:
        return registry.latest(current.kind)

    return resolve


def earliest_target_resolver(
    registry: Registry[VersionValue, ModelBase],
) -> TargetResolver:
    """A resolver that converges to the earliest registered version per kind."""

    def resolve(
        current: Versionable[VersionValue_co, VModel_co],
    ) -> Versionable[VersionValue_co, VModel_co] | None:
        return registry.earliest(current.kind)

    return resolve


def fixed_target_resolver(
    registry: Registry[VersionValue, ModelBase],
    target: Versionable[VersionValue, ModelBase],
) -> TargetResolver:
    """A resolver that always returns *target* for its kind.

    *target* is validated against *registry* immediately.
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
    """Compose per-kind resolvers into one dispatcher.

    The special key ``"*"`` is the fallback for kinds not explicitly listed.
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
