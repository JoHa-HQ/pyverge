"""Migration-local type surface: execution/transport protocols and entry types.

These reference the migration graph and registry, so they belong to the
migration package rather than the provider-neutral core type module.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any, Protocol

from pyverge.core.types import (
    DirectionViolationStrategy,
    MigrationDirectionStrategy,
    ModelData,
    Versionable,
    VersionMissingStrategy,
    VersionValue,
    VersionValue_co,
)

if TYPE_CHECKING:
    from pyverge.providers.types import ModelAdapter

    from .graph import GraphEntry, MigrationPlan
    from .registry import Registry

#: A discovered versioned entry: ``(path, depth, source)``.
Entry = tuple[tuple[str | int, ...], int, "Versionable[VersionValue]"]

MigrationEntryCallback = Callable[
    [Any, Any, ModelData, tuple[Any, ...], str],
    ModelData,
]


class Walker(Protocol[VersionValue_co]):
    """Protocol for schema-aware payload discovery."""

    @property
    def registry(self) -> Registry[VersionValue_co]: ...

    def discover(
        self,
        data: dict[str, Any],
        *,
        container: type[Any] | None = None,
        target_resolver: Any,
        max_depth: int = -1,
    ) -> Iterator[Entry]: ...


class RunnableMigration(Protocol):
    """Deferred migration of a single graph entry."""

    def run(self) -> ModelData: ...


class Executor(Protocol[VersionValue_co]):
    """Protocol for executing a migration plan.

    The executor owns the pre-execution compatibility gate: it validates the
    plan's container against the graph's migrated fields before any migration
    runs.
    """

    def run(
        self,
        plan: MigrationPlan[VersionValue_co],
        *,
        registry: Registry[VersionValue_co],
        entry_migration: MigrationEntry[VersionValue_co],
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
    ) -> ModelData: ...


class MigrationEntry(Protocol[VersionValue]):
    """Per-entry migration policy."""

    def migrate(
        self,
        entry: GraphEntry[VersionValue],
        current: ModelData,
        *,
        execute_step: MigrationEntryCallback,
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
    ) -> RunnableMigration: ...
