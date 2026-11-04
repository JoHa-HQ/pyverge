from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import anyio

from pyverge.core.types import VersionValue
from pyverge.runtime.context import RunContext
from pyverge.runtime.hooks.state import new_hook_state
from pyverge.runtime.plan import EntryResult, ExecutionEntry, ExecutionPlan
from pyverge.runtime.strategies import AsyncStrategy
from pyverge.schemas.types import ModelIdentityPort

_STRATEGY = AsyncStrategy()


@dataclass(frozen=True, slots=True)
class AsyncBackend:
    """Run sync migrations in threads and coroutines natively."""

    backend: str
    backend_options: Mapping[str, Any]
    max_workers: int = 0

    async def execute(
        self,
        plan: ExecutionPlan[VersionValue],
        payload: dict[str, Any],
        run: RunContext,
        adapter: ModelIdentityPort,
    ) -> dict[str, Any]:
        data = payload
        hook_state = new_hook_state()
        for level in plan.levels:
            if self.max_workers > 1:
                limiter = anyio.CapacityLimiter(self.max_workers)
                results: list[EntryResult | None] = [None] * len(level)
                async with anyio.create_task_group() as group:
                    for index, entry in enumerate(level):
                        group.start_soon(
                            self._execute_entry_limited,
                            index,
                            entry,
                            plan,
                            data,
                            run,
                            adapter,
                            hook_state,
                            limiter,
                            results,
                        )
                level_results = tuple(
                    result for result in results if result is not None
                )
            else:
                level_results = tuple(
                    [
                        await self._execute_entry(
                            entry,
                            plan,
                            data,
                            run,
                            adapter,
                            hook_state,
                        )
                        for entry in level
                    ]
                )
            data = plan.apply_results(data, level_results)
        return data

    async def _execute_entry_limited(  # noqa: PLR0913, PLR0917
        self,
        index: int,
        entry: ExecutionEntry[VersionValue],
        plan: ExecutionPlan[VersionValue],
        data: dict[str, Any],
        run: RunContext,
        adapter: ModelIdentityPort,
        hook_state: Any,
        limiter: anyio.CapacityLimiter,
        results: list[EntryResult | None],
    ) -> None:
        async with limiter:
            results[index] = await self._execute_entry(
                entry,
                plan,
                data,
                run,
                adapter,
                hook_state,
            )

    async def _execute_entry(  # noqa: PLR0913, PLR0917
        self,
        entry: ExecutionEntry[VersionValue],
        plan: ExecutionPlan[VersionValue],
        data: dict[str, Any],
        run: RunContext,
        adapter: ModelIdentityPort,
        hook_state: Any,
    ) -> EntryResult:
        return await entry.execute_async(
            plan.entry_value(data, entry),
            run=run,
            adapter=adapter,
            hook_state=hook_state,
            invoke=_STRATEGY.invoke,
        )


__all__ = ["AsyncBackend"]
