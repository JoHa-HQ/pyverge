from __future__ import annotations

import copy
import inspect
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pyverge.core.context import MigrationContext
from pyverge.core.types import VersionValue
from pyverge.execution.context import RunContext, StepContext
from pyverge.execution.errors import AsyncExecutionRequired
from pyverge.execution.hooks.state import new_hook_state
from pyverge.execution.plan import ExecutionPlan, PathPlanEntry
from pyverge.graph.planning.path import Path
from pyverge.schemas.types import ModelIdentityPort
from pyverge.versioning import EdgeKey


class ThreadedBackend:
    """Run migrations directly, or in a thread pool when workers > 1."""

    def __init__(self, max_workers: int) -> None:
        self._max_workers = max_workers

    def execute(
        self,
        plan: ExecutionPlan[VersionValue],
        payload: dict[str, Any],
        run: RunContext,
        adapter: ModelIdentityPort,
    ) -> dict[str, Any]:
        data = copy.deepcopy(payload)
        hook_state = new_hook_state()
        for level in plan.levels:
            if self._max_workers > 1:
                with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
                    list(
                        pool.map(
                            lambda entry: self._execute_entry(
                                entry, data, run, adapter, hook_state
                            ),
                            level,
                        )
                    )
            else:
                for entry in level:
                    self._execute_entry(entry, data, run, adapter, hook_state)
        return data

    def _execute_entry(  # noqa: C901, PLR0912
        self,
        entry: PathPlanEntry[VersionValue],
        data: dict[str, Any],
        run: RunContext,
        adapter: ModelIdentityPort,
        hook_state: Any,
    ) -> None:
        current = Path(*entry.path).get(data)
        for index, (source, target) in enumerate(entry.steps):
            func = entry.migrations[index]
            hooks = entry.hooks[index]
            name = getattr(func, "__name__", f"{source}->{target}")
            migration = (
                entry.migration_descriptors[index]
                if index < len(entry.migration_descriptors)
                else None
            )
            for hook in hooks:
                result = hook.before_migrate(
                    name,
                    source,
                    target,
                    current,
                    migration=migration,
                    state=hook_state,
                )
                if inspect.isawaitable(result):
                    if inspect.iscoroutine(result):
                        result.close()
                    raise AsyncExecutionRequired("async hook requires async backend")
            step = self._step(entry, index, source, target, run)
            try:
                migrated = func(current, step.view)
                if inspect.isawaitable(migrated):
                    if inspect.iscoroutine(migrated):
                        migrated.close()
                    raise AsyncExecutionRequired(
                        "coroutine migration requires async backend"
                    )
            except Exception as error:
                for hook in hooks:
                    result = hook.on_error(
                        name,
                        source,
                        target,
                        current,
                        error,
                        migration=migration,
                        state=hook_state,
                    )
                    if inspect.isawaitable(result):
                        if inspect.iscoroutine(result):
                            result.close()
                        raise AsyncExecutionRequired(
                            "async hook requires async backend"
                        )
                raise
            for hook in hooks:
                result = hook.after_migrate(
                    name,
                    source,
                    target,
                    current,
                    migrated,
                    migration=migration,
                    state=hook_state,
                )
                if inspect.isawaitable(result):
                    if inspect.iscoroutine(result):
                        result.close()
                    raise AsyncExecutionRequired("async hook requires async backend")
            if isinstance(migrated, dict):
                migrated[adapter.version_property] = str(target.version)
            current = migrated
        Path(*entry.path).set(data, current)

    def _step(
        self,
        entry: PathPlanEntry[VersionValue],
        index: int,
        source: Any,
        target: Any,
        run: RunContext,
    ) -> StepContext:
        return StepContext(
            run=run,
            path=entry.path,
            index=index,
            source=source,
            target=target,
            edge=EdgeKey.from_pair(source, target),
            bindings=MigrationContext.empty(),
        )


__all__ = ["ThreadedBackend"]
