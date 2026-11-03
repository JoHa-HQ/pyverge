from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from pyverge.core.types import VersionValue
from pyverge.runtime.context import RunContext
from pyverge.runtime.hooks.state import new_hook_state
from pyverge.runtime.plan import EntryResult, ExecutionEntry, ExecutionPlan
from pyverge.runtime.strategies import ThreadedStrategy
from pyverge.schemas.types import ModelIdentityPort


class ThreadedBackend:
    """Run migrations directly, or in a thread pool when workers > 1."""

    def __init__(self, max_workers: int) -> None:
        self._max_workers = max_workers
        self._strategy = ThreadedStrategy()

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
                    results = tuple(
                        pool.map(
                            lambda entry: self._run_entry(
                                entry, plan, data, run, adapter, hook_state
                            ),
                            level,
                        )
                    )
            else:
                results = tuple(
                    self._run_entry(entry, plan, data, run, adapter, hook_state)
                    for entry in level
                )
            data = plan.apply_results(data, results)
        return data

    def _run_entry(  # noqa: PLR0913, PLR0917
        self,
        entry: ExecutionEntry[VersionValue],
        plan: ExecutionPlan[VersionValue],
        data: dict[str, Any],
        run: RunContext,
        adapter: ModelIdentityPort,
        hook_state: Any,
    ) -> EntryResult:
        return entry.execute_sync(
            plan.entry_value(data, entry),
            run=run,
            adapter=adapter,
            hook_state=hook_state,
            invoke=self._strategy.invoke,
        )


__all__ = ["ThreadedBackend"]
