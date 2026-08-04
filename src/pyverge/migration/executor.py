from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Generic

from .exceptions import MigrationError, MigrationNotFoundError
from .graph import GraphEntry, MigrationGraph
from .registry import Registry
from .steps import ExplicitStep
from .types import (
    Attachable,
    DirectionViolationStrategy,
    Executor,
    MigrationDirectionStrategy,
    ModelAdapter,
    ModelData,
    Versionable,
    VersionMissingStrategy,
    VersionValue,
    VModel,
    VSource,
    VTarget,
)
from .versioning import SentinelEdge

if TYPE_CHECKING:
    from .strategy import EntryMigration


class StepExecutor(Generic[VersionValue]):
    """Resolves and runs a single migration step from the registry."""

    def __init__(self, registry: Registry[VersionValue]) -> None:
        self._registry = registry

    def execute_step(
        self,
        step_from: Versionable[VersionValue, VModel],
        step_to: Versionable[VersionValue, VModel],
        data: ModelData,
        hooks: tuple[Attachable, ...],
        vp: str,
    ) -> ModelData:
        """Execute a single migration step and update the version property."""
        step = self._resolve_step(step_from, step_to)
        hooks_list = list(hooks)
        try:
            result = step.execute(data, hooks_list)
        except MigrationError:
            raise
        except Exception as exc:
            for hook in hooks_list:
                hook.on_error(str(step_from.kind), step_from, step_to, data, exc)
            raise MigrationError(
                str(step_from.kind),
                step_from,
                step_to,
                f"Migration failed: {type(exc).__name__}: {exc}",
            ) from exc

        result[vp] = str(step_to.version[1])
        return result

    def _resolve_step(
        self,
        step_from: Versionable[VersionValue, VModel],
        step_to: Versionable[VersionValue, VModel],
    ) -> ExplicitStep[VersionValue, VSource, VTarget]:
        """Resolve an edge to an explicit migration step."""
        key = SentinelEdge.from_pair(step_from, step_to)
        if self._registry.has_migration(key):
            return ExplicitStep[VersionValue, VSource, VTarget](
                self._registry.get_migration(key)
            )
        raise MigrationNotFoundError(
            self._registry.name,
            (step_from, step_to),
        )


class SequentialExecutor(Executor):
    """Execute graph entries one at a time in topological order."""

    def run(
        self,
        data: ModelData,
        graph: MigrationGraph[VersionValue],
        *,
        registry: Registry[VersionValue],
        entry_migration: EntryMigration[VersionValue],
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
    ) -> ModelData:
        step_executor = StepExecutor(registry)
        result = copy.deepcopy(data)
        for entry in graph.topological_order():
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
            )
            migrated = task.run()
            _set_at_path(result, entry.path, migrated)
        return result


class LevelParallelExecutor(Executor):
    """Execute independent graph entries within each topological level in parallel.

    Args:
        max_workers: Maximum number of worker threads per execution wave.
    """

    def __init__(self, max_workers: int | None = None) -> None:
        self._max_workers = max_workers

    def run(
        self,
        data: ModelData,
        graph: MigrationGraph[VersionValue],
        *,
        registry: Registry[VersionValue],
        entry_migration: EntryMigration[VersionValue],
        adapter: ModelAdapter,
        version_property: str,
        direction: MigrationDirectionStrategy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
    ) -> ModelData:
        step_executor = StepExecutor(registry)
        result = copy.deepcopy(data)
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
    entry_migration: EntryMigration[VersionValue],
    step_executor: StepExecutor,
    adapter: ModelAdapter,
    version_property: str,
    direction: MigrationDirectionStrategy,
    on_direction_violation: DirectionViolationStrategy,
    on_missing_path: VersionMissingStrategy,
    entry: GraphEntry[VersionValue, VModel],
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
    ).run()


def _get_at_path(
    data: ModelData,
    path: tuple[str | int, ...],
) -> ModelData:
    """Return the value at *path* inside *data*."""
    if not path:
        return data
    current: Any = data
    for step in path:
        current = current[step]
    return current


def _set_at_path(
    data: ModelData,
    path: tuple[str | int, ...],
    value: ModelData,
) -> None:
    """Write *value* into *data* at *path*, mutating *data* in place."""
    if not path:
        data.clear()
        data.update(value)
        return
    current: Any = data
    for step in path[:-1]:
        current = current[step]
    current[path[-1]] = value
