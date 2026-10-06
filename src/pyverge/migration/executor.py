from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor as _ThreadPoolExecutor
from typing import Generic

from pyverge.core.exceptions import (
    DiscoveryValidationError,
    MigrationError,
    MigrationNotFoundError,
)
from pyverge.core.path import get_at as _get_at_path
from pyverge.core.path import set_at as _set_at_path
from pyverge.core.steps import ExplicitStep
from pyverge.core.types import (
    Attachable,
    DirectionViolationStrategy,
    MigrationDirectionStrategy,
    ModelData,
    Versionable,
    VersionMissingStrategy,
    VersionValue,
)
from pyverge.core.versioning import (
    SentinelEdge,
)
from pyverge.migration.types import (
    Executor,
    MigrationEntry,
)
from pyverge.providers.types import (
    ModelAdapter,
)

from .graph import GraphEntry, MigrationPlan
from .registry import Registry


def _check_container_compatibility(
    adapter: ModelAdapter,
    plan: MigrationPlan,
) -> None:
    """Fail fast when the plan's container cannot cover the migrated fields.

    Runs before any migration: if the container is not recognized, or does not
    declare every field the graph will produce, discovery of the migrated shape
    cannot be trusted — raise before executing.
    """
    container = plan.container
    if container is None:
        return
    fields: set[str] = set()
    for entry in plan.graph.entries:
        fields.update(entry.target.fields)
    if not adapter.can_handle(container, fields=frozenset(fields)):
        raise DiscoveryValidationError(
            path=(),
            message=(
                "container is incompatible with the migration graph: "
                f"cannot cover fields {sorted(fields)}"
            ),
        )


class StepExecutor(Generic[VersionValue]):
    """Resolves and runs a single migration step from the registry."""

    def __init__(self, registry: Registry[VersionValue]) -> None:
        self._registry = registry

    def execute_step(
        self,
        step_from: Versionable[VersionValue],
        step_to: Versionable[VersionValue],
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
        step_from: Versionable[VersionValue],
        step_to: Versionable[VersionValue],
    ) -> ExplicitStep[VersionValue]:
        """Resolve an edge to an explicit migration step."""
        key = SentinelEdge.from_pair(step_from, step_to)
        if self._registry.has_migration(key):
            return ExplicitStep[VersionValue](self._registry.get_migration(key))
        raise MigrationNotFoundError(
            self._registry.name,
            (step_from, step_to),
        )


class SequentialExecutor(Executor[VersionValue]):
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
    ) -> ModelData:
        _check_container_compatibility(adapter, plan)
        graph = plan.graph
        step_executor = StepExecutor(registry)
        result = copy.deepcopy(plan.data)
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


class LevelParallelExecutor(Executor[VersionValue]):
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
    ) -> ModelData:
        _check_container_compatibility(adapter, plan)
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
    entry_migration: MigrationEntry[VersionValue],
    step_executor: StepExecutor,
    adapter: ModelAdapter,
    version_property: str,
    direction: MigrationDirectionStrategy,
    on_direction_violation: DirectionViolationStrategy,
    on_missing_path: VersionMissingStrategy,
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
    ).run()
