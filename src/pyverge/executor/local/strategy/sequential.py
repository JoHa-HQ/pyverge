"""Sequential plan execution."""

from __future__ import annotations

import copy
from typing import Generic

from pyverge.core.context import MigrationContext
from pyverge.core.path import get_at as _get_at_path
from pyverge.core.path import set_at as _set_at_path
from pyverge.core.types import (
    DirectionViolationStrategy,
    MigrationDirectionStrategy,
    ModelData,
    VersionMissingStrategy,
    VersionValue,
)
from pyverge.migration.graph import MigrationPlan
from pyverge.migration.registry import Registry
from pyverge.providers.types import ModelAdapter

from ...ports import AsyncExecutionStrategy, ExecutionBackend, SyncExecutionStrategy
from ...types import (
    AsyncExecutor,
    AsyncMigrationEntry,
    Executor,
    MigrationEntry,
)
from ..backend import LocalExecutionBackend


def _backend(
    registry: Registry[VersionValue],
    entry_migration: MigrationEntry[VersionValue] | AsyncMigrationEntry[VersionValue],
    adapter: ModelAdapter,
    version_property: str,
    direction: MigrationDirectionStrategy,
    on_direction_violation: DirectionViolationStrategy,
    on_missing_path: VersionMissingStrategy,
) -> LocalExecutionBackend[VersionValue]:
    return LocalExecutionBackend(
        registry=registry,
        entry_migration=entry_migration,
        adapter=adapter,
        version_property=version_property,
        direction=direction,
        on_direction_violation=on_direction_violation,
        on_missing_path=on_missing_path,
    )


class SequentialExecutor(
    Executor[VersionValue],
    SyncExecutionStrategy[VersionValue],
    Generic[VersionValue],
):
    """Execute plan entries one at a time in topological order."""

    def run(
        self,
        plan: MigrationPlan[VersionValue],
        *,
        registry: Registry[VersionValue],
        entry_migration: MigrationEntry[VersionValue],
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
        context: MigrationContext | None = None,
    ) -> ModelData:
        return self.execute(
            plan,
            _backend(
                registry,
                entry_migration,
                adapter,
                version_property,
                direction,
                on_direction_violation,
                on_missing_path,
            ),
            context=context,
        )

    def execute(
        self,
        plan: MigrationPlan[VersionValue],
        backend: ExecutionBackend[VersionValue],
        *,
        context: MigrationContext | None = None,
    ) -> ModelData:
        backend.ensure_compatible(plan)
        result = copy.deepcopy(plan.data)
        for entry in plan.graph.topological_order():
            current = _get_at_path(result, entry.path)
            migrated = backend.run_entry(entry, current, context)
            _set_at_path(result, entry.path, migrated)
        return result


class AsyncSequentialExecutor(
    AsyncExecutor[VersionValue],
    AsyncExecutionStrategy[VersionValue],
    Generic[VersionValue],
):
    """Execute plan entries one at a time with async step/hook handling."""

    async def arun(
        self,
        plan: MigrationPlan[VersionValue],
        *,
        registry: Registry[VersionValue],
        entry_migration: AsyncMigrationEntry[VersionValue],
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
        context: MigrationContext | None = None,
    ) -> ModelData:
        return await self.aexecute(
            plan,
            _backend(
                registry,
                entry_migration,
                adapter,
                version_property,
                direction,
                on_direction_violation,
                on_missing_path,
            ),
            context=context,
        )

    async def aexecute(
        self,
        plan: MigrationPlan[VersionValue],
        backend: ExecutionBackend[VersionValue],
        *,
        context: MigrationContext | None = None,
    ) -> ModelData:
        backend.ensure_compatible(plan)
        result = copy.deepcopy(plan.data)
        for entry in plan.graph.topological_order():
            current = _get_at_path(result, entry.path)
            migrated = await backend.arun_entry(entry, current, context)
            _set_at_path(result, entry.path, migrated)
        return result
