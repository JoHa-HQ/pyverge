from __future__ import annotations

import copy
from concurrent.futures import ProcessPoolExecutor
from typing import Any

from pyverge.core.types import VersionValue
from pyverge.runtime.context import RunContext
from pyverge.runtime.hooks.state import new_hook_state
from pyverge.runtime.plan import ExecutionPlan
from pyverge.runtime.strategies import ProcessStrategy
from pyverge.schemas.types import ModelIdentityPort


class ProcessBackend:
    """Run migration callables in a process pool; hooks stay in the parent."""

    def __init__(self, max_workers: int) -> None:
        self._executor = ProcessPoolExecutor(max_workers=max_workers)
        self._strategy = ProcessStrategy(self._executor)

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
            results = tuple(
                entry.execute_sync(
                    plan.entry_value(data, entry),
                    run=run,
                    adapter=adapter,
                    hook_state=hook_state,
                    invoke=self._strategy.invoke,
                )
                for entry in level
            )
            data = plan.apply_results(data, results)
        return data

    def close(self) -> None:
        self._executor.shutdown()


__all__ = ["ProcessBackend"]
