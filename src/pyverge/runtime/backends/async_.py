from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import anyio

from pyverge.core.graph.planning.path import Path
from pyverge.core.types import VersionValue
from pyverge.core.versioning import EdgeKey
from pyverge.runtime.context import MigrationContext, RunContext, StepContext
from pyverge.runtime.hooks.state import new_hook_state
from pyverge.runtime.plan import ExecutionEntry, ExecutionPlan
from pyverge.schemas.types import ModelIdentityPort


@dataclass(frozen=True, slots=True)
class AsyncBackend:
    """Run sync migrations in threads and coroutines natively."""

    backend: str
    backend_options: Mapping[str, Any]
    max_workers: int = 0

    async def __aenter__(self) -> AsyncBackend:
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    async def execute(
        self,
        plan: ExecutionPlan[VersionValue],
        payload: dict[str, Any],
        run: RunContext,
        adapter: ModelIdentityPort,
    ) -> dict[str, Any]:
        data = copy.deepcopy(payload)
        hook_state = new_hook_state()
        for level in plan.levels:
            if self.max_workers > 1:
                limiter = anyio.CapacityLimiter(self.max_workers)
                async with anyio.create_task_group() as group:
                    for entry in level:
                        group.start_soon(
                            self._execute_entry_limited,
                            entry,
                            data,
                            run,
                            adapter,
                            hook_state,
                            limiter,
                        )
            else:
                for entry in level:
                    await self._execute_entry(entry, data, run, adapter, hook_state)
        return data

    async def _execute_entry_limited(  # noqa: PLR0913, PLR0917
        self, entry, data, run, adapter, hook_state, limiter
    ) -> None:
        async with limiter:
            await self._execute_entry(entry, data, run, adapter, hook_state)

    async def _execute_entry(
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
            migrated = await entry.step(index).run_async(
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
            edge=EdgeKey.from_pair(source, target),
            bindings=MigrationContext.empty(),
        )


__all__ = ["AsyncBackend"]
