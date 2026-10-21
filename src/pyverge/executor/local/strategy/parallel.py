"""Level-parallel plan execution (thread pool / asyncio gather)."""

from __future__ import annotations

import asyncio
import copy
from collections.abc import Awaitable
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor
from typing import Generic

from pyverge.core.context import MigrationContext
from pyverge.core.exceptions import MigrationError
from pyverge.core.path import get_at as _get_at_path
from pyverge.core.path import set_at as _set_at_path
from pyverge.core.types import (
    DirectionViolationStrategy,
    MigrationDirectionStrategy,
    ModelData,
    VersionMissingStrategy,
    VersionValue,
)
from pyverge.migration.graph import GraphEntry, MigrationPlan
from pyverge.migration.registry import Registry
from pyverge.providers.types import ModelAdapter

from ...ports import AsyncExecutionStrategy, ExecutionBackend, SyncExecutionStrategy
from ...types import (
    AsyncExecutor,
    AsyncMigrationEntry,
    Executor,
    MigrationEntry,
)
from .sequential import _backend


class LevelParallelExecutor(
    Executor[VersionValue],
    SyncExecutionStrategy[VersionValue],
    Generic[VersionValue],
):
    """Execute independent plan entries within each topological level in parallel.

    Args:
        max_workers: Maximum number of worker threads per execution wave.
    """

    def __init__(self, max_workers: int | None = None) -> None:
        self._max_workers = max_workers

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
        for level in plan.graph.execution_levels():
            if len(level) == 1:
                entry = level[0]
                current = _get_at_path(result, entry.path)
                migrated = backend.run_entry(entry, current, context)
                _set_at_path(result, entry.path, migrated)
                continue

            with _ThreadPoolExecutor(max_workers=self._max_workers) as pool:
                futures = {
                    pool.submit(
                        _run_entry,
                        backend,
                        entry,
                        _get_at_path(result, entry.path),
                        context,
                    ): entry
                    for entry in level
                }
                for future, entry in futures.items():
                    try:
                        migrated = future.result()
                    except Exception as exc:
                        raise MigrationError(
                            entry.kind,
                            entry.source,
                            entry.target,
                            f"Migration failed at {entry.path}: {exc}",
                        ) from exc
                    _set_at_path(result, entry.path, migrated)
        return result


class AsyncLevelParallelExecutor(
    AsyncExecutor[VersionValue],
    AsyncExecutionStrategy[VersionValue],
    Generic[VersionValue],
):
    """Execute independent entries per level with ``asyncio.gather``."""

    def __init__(self, max_workers: int | None = None) -> None:
        self._max_workers = max_workers

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
        semaphore = asyncio.Semaphore(self._max_workers) if self._max_workers else None
        for level in plan.graph.execution_levels():
            if len(level) == 1:
                entry = level[0]
                current = _get_at_path(result, entry.path)
                migrated = await backend.arun_entry(entry, current, context)
                _set_at_path(result, entry.path, migrated)
                continue

            outcomes = await asyncio.gather(
                *(
                    _limited_await(
                        semaphore,
                        _run_entry_async(
                            backend,
                            entry,
                            _get_at_path(result, entry.path),
                            context,
                        ),
                    )
                    for entry in level
                ),
                return_exceptions=True,
            )
            for entry, outcome in zip(level, outcomes):
                if isinstance(outcome, BaseException):
                    raise MigrationError(
                        entry.kind,
                        entry.source,
                        entry.target,
                        f"Migration failed at {entry.path}: {outcome}",
                    ) from outcome
                _set_at_path(result, entry.path, outcome)
        return result


def _run_entry(
    backend: ExecutionBackend[VersionValue],
    entry: GraphEntry[VersionValue],
    current: ModelData,
    context: MigrationContext | None,
) -> ModelData:
    return backend.run_entry(entry, current, context)


async def _run_entry_async(
    backend: ExecutionBackend[VersionValue],
    entry: GraphEntry[VersionValue],
    current: ModelData,
    context: MigrationContext | None,
) -> ModelData:
    return await backend.arun_entry(entry, current, context)


async def _limited_await(
    semaphore: asyncio.Semaphore | None,
    awaitable: Awaitable[ModelData],
) -> ModelData:
    """Await *awaitable* under *semaphore*, or directly when unset."""
    if semaphore is None:
        return await awaitable
    async with semaphore:
        return await awaitable
