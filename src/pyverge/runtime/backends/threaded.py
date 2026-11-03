from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pyverge.core.graph.planning.path import Path
from pyverge.core.types import VersionValue
from pyverge.runtime.context import MigrationContext, RunContext, StepContext
from pyverge.runtime.hooks.state import new_hook_state
from pyverge.runtime.plan import ExecutionEntry, ExecutionPlan
from pyverge.schemas.types import ModelIdentityPort


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
            step = self._step(entry, index, source, target, run)
            migrated = entry.step(index).run_sync(
                current,
                step.view,
                name=name,
                hook_state=hook_state,
            )
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


__all__ = ["ThreadedBackend"]
