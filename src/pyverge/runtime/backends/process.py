from __future__ import annotations

import copy
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from pyverge.core.graph.planning.path import Path
from pyverge.core.types import VersionValue
from pyverge.runtime.context import MigrationContext, RunContext, StepContext
from pyverge.runtime.hooks.state import new_hook_state
from pyverge.runtime.plan import ExecutionEntry, ExecutionPlan
from pyverge.schemas.types import ModelIdentityPort


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
        hook_state = new_hook_state()
        for level in plan.levels:
            for entry in level:
                self._execute_entry(entry, data, run, adapter, hook_state)
        return data

    def _execute_entry(
        self,
        entry: ExecutionEntry[VersionValue],
        data: dict[str, Any],
        run: RunContext,
        adapter: ModelIdentityPort,
        hook_state: Any,
    ) -> None:
        current = Path(*entry.path).get(data)
        for index, (source, target) in enumerate(entry.steps):
            name = getattr(
                entry.migration_func(index), "__name__", f"{source}->{target}"
            )
            invoker = entry.step(index)
            invoker.before(current, name, hook_state)
            step = self._step(entry, index, source, target, run)
            try:
                migrated = self._executor.submit(
                    _invoke, entry.migration_func(index), current, dict(step.view)
                ).result()
            except Exception as error:
                invoker.on_error(current, error, name, hook_state)
                raise
            invoker.after(current, migrated, name, hook_state)
            if isinstance(migrated, dict):
                migrated[adapter.version_property] = str(target.version)
            current = migrated
        Path(*entry.path).set(data, current)

    def _step(
        self,
        entry: ExecutionEntry[VersionValue],
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
            edge=entry.plan.edges[index],
            bindings=MigrationContext.empty(),
        )

    def close(self) -> None:
        self._executor.shutdown()


__all__ = ["ProcessBackend"]
