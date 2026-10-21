"""Level-parallel plan execution (thread pool)."""

from __future__ import annotations

import copy
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

from .step import StepExecutor
from .types import Executor, MigrationEntry


class LevelParallelExecutor(Executor[VersionValue], Generic[VersionValue]):
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
        adapter.ensure_compatible(plan.container, fields=plan.target_fields)
        graph = plan.graph
        step_executor = StepExecutor(registry)
        result = copy.deepcopy(plan.data)
        levels = graph.execution_levels()
        for level in levels:
            if len(level) == 1:
                entry = level[0]
                current = _get_at_path(result, entry.path)
                task = entry_migration.migrate(
                    entry,
                    current,
                    execute_step=step_executor.execute_step,
                    adapter=adapter,
                    version_property=version_property,
                    direction=direction,
                    on_direction_violation=on_direction_violation,
                    on_missing_path=on_missing_path,
                    context=context,
                )
                migrated = task.run()
                _set_at_path(result, entry.path, migrated)
                continue

            with _ThreadPoolExecutor(max_workers=self._max_workers) as pool:
                futures = {
                    pool.submit(
                        _run_task,
                        entry_migration,
                        step_executor,
                        adapter,
                        version_property,
                        direction,
                        on_direction_violation,
                        on_missing_path,
                        context,
                        entry,
                        _get_at_path(result, entry.path),
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


def _run_task(
    entry_migration: MigrationEntry[VersionValue],
    step_executor: StepExecutor,
    adapter: ModelAdapter,
    version_property: str,
    direction: MigrationDirectionStrategy,
    on_direction_violation: DirectionViolationStrategy,
    on_missing_path: VersionMissingStrategy,
    context: MigrationContext | None,
    entry: GraphEntry[VersionValue],
    current: ModelData,
) -> ModelData:
    """Helper for running a task inside a thread pool."""
    return entry_migration.migrate(
        entry,
        current,
        execute_step=step_executor.execute_step,
        adapter=adapter,
        version_property=version_property,
        direction=direction,
        on_direction_violation=on_direction_violation,
        on_missing_path=on_missing_path,
        context=context,
    ).run()
