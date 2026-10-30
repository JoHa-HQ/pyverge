from __future__ import annotations

import copy
import inspect
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from pyverge.core.context import MigrationContext
from pyverge.core.types import VersionValue
from pyverge.execution.context import RunContext, StepContext
from pyverge.execution.errors import AsyncExecutionRequired
from pyverge.execution.plan import ExecutionPlan, PathPlanEntry
from pyverge.graph.planning.path import Path
from pyverge.schemas.types import ModelIdentityPort
from pyverge.versioning import EdgeKey


def _invoke(work: Any, data: Any, context: Any) -> Any:
    return work(data, context)


class ProcessBackend:
    """Run migration callables in a process pool; hooks stay in the parent."""

    def __init__(self, max_workers: int) -> None:
        self._executor = ProcessPoolExecutor(max_workers=max_workers)

    def execute(
        self,
        plan: ExecutionPlan[VersionValue],
        payload: dict[str, Any],
        run: RunContext,
        adapter: ModelIdentityPort,
    ) -> dict[str, Any]:
        data = copy.deepcopy(payload)
        for level in plan.levels:
            for entry in level:
                self._execute_entry(entry, data, run, adapter)
        return data

    def _execute_entry(
        self,
        entry: PathPlanEntry[VersionValue],
        data: dict[str, Any],
        run: RunContext,
        adapter: ModelIdentityPort,
    ) -> None:
        current = Path(*entry.path).get(data)
        for index, (source, target) in enumerate(entry.steps):
            func = entry.migrations[index]
            hooks = entry.hooks[index]
            name = getattr(func, "__name__", f"{source}->{target}")
            for hook in hooks:
                result = hook.before_migrate(name, source, target, current)
                if inspect.isawaitable(result):
                    if inspect.iscoroutine(result):
                        result.close()
                    raise AsyncExecutionRequired("async hook requires async backend")
            step = self._step(entry, index, source, target, run)
            try:
                migrated = self._executor.submit(
                    _invoke, func, current, dict(step.view)
                ).result()
            except Exception as error:
                for hook in hooks:
                    hook.on_error(name, source, target, current, error)
                raise
            for hook in hooks:
                hook.after_migrate(name, source, target, current, migrated)
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

    def close(self) -> None:
        self._executor.shutdown()


__all__ = ["ProcessBackend"]
