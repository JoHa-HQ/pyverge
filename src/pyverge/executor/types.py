"""Execution-local type surface: protocols for plan execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pyverge.core.context import MigrationContext
from pyverge.core.types import (
    Attachable,
    DirectionViolationStrategy,
    MigrationDirectionStrategy,
    ModelData,
    Versionable,
    VersionMissingStrategy,
    VersionValue_co,
)

if TYPE_CHECKING:
    from pyverge.migration.graph import GraphEntry, MigrationPlan
    from pyverge.migration.registry import Registry
    from pyverge.providers.types import ModelAdapter

MigrationEntryCallback = Callable[
    [
        Versionable,
        Versionable,
        ModelData,
        tuple[Attachable, ...],
        str,
        MigrationContext | None,
    ],
    ModelData,
]


class RunnableMigration(Protocol):
    """Deferred migration of a single graph entry."""

    def run(self) -> ModelData: ...


class AsyncRunnableMigration(Protocol):
    """Deferred async migration of a single graph entry."""

    async def arun(self) -> ModelData: ...


AsyncMigrationEntryCallback = Callable[
    [
        Versionable,
        Versionable,
        ModelData,
        tuple[Attachable, ...],
        str,
        MigrationContext | None,
    ],
    Awaitable[ModelData],
]


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
        context: MigrationContext | None = None,
    ) -> ModelData: ...


@runtime_checkable
class AsyncExecutor(Protocol[VersionValue_co]):
    """Protocol for asynchronously executing a migration plan."""

    async def arun(
        self,
        plan: MigrationPlan[VersionValue_co],
        *,
        registry: Registry[VersionValue_co],
        entry_migration: AsyncMigrationEntry[VersionValue_co],
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
        context: MigrationContext | None = None,
    ) -> ModelData: ...


class MigrationEntry(Protocol[VersionValue_co]):
    """Per-entry migration policy."""

    def migrate(
        self,
        entry: GraphEntry[VersionValue_co],
        current: ModelData,
        *,
        execute_step: MigrationEntryCallback,
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
        context: MigrationContext | None = None,
    ) -> RunnableMigration: ...


class AsyncMigrationEntry(Protocol[VersionValue_co]):
    """Async per-entry migration policy."""

    def amigrate(
        self,
        entry: GraphEntry[VersionValue_co],
        current: ModelData,
        *,
        aexecute_step: AsyncMigrationEntryCallback,
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
        context: MigrationContext | None = None,
    ) -> AsyncRunnableMigration: ...
