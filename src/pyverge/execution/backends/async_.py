from __future__ import annotations

import copy
import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from functools import partial
from typing import Any

import anyio

from pyverge.core.context import MigrationContext
from pyverge.core.types import VersionValue
from pyverge.execution.context import RunContext, StepContext
from pyverge.execution.path import Path
from pyverge.execution.plan import ExecutionPlan, PathPlanEntry
from pyverge.schemas.types import ModelAdapter
from pyverge.versioning import EdgeKey


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
        adapter: ModelAdapter,
    ) -> dict[str, Any]:
        data = copy.deepcopy(payload)
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
                            limiter,
                        )
            else:
                for entry in level:
                    await self._execute_entry(entry, data, run, adapter)
        return data

    async def _execute_entry_limited(self, entry, data, run, adapter, limiter) -> None:
        async with limiter:
            await self._execute_entry(entry, data, run, adapter)

    async def _execute_entry(
        self,
        entry: PathPlanEntry[VersionValue],
        data: dict[str, Any],
        run: RunContext,
        adapter: ModelAdapter,
    ) -> None:
        current = Path(*entry.path).get(data)
        for index, (source, target) in enumerate(entry.steps):
            func = entry.migrations[index]
            hooks = entry.hooks[index]
            name = getattr(func, "__name__", f"{source}->{target}")
            for hook in hooks:
                result = hook.before_migrate(name, source, target, current)
                if inspect.isawaitable(result):
                    await result
            step = self._step(entry, index, source, target, run)
            try:
                migrated = await self._invoke(func, current, step.view)
            except Exception as error:
                for hook in hooks:
                    result = hook.on_error(name, source, target, current, error)
                    if inspect.isawaitable(result):
                        await result
                raise
            for hook in hooks:
                result = hook.after_migrate(name, source, target, current, migrated)
                if inspect.isawaitable(result):
                    await result
            if isinstance(migrated, dict):
                migrated[adapter.version_property] = str(target.version)
            current = migrated
        Path(*entry.path).set(data, current)

    async def _invoke(self, func: Any, data: Any, context: Any) -> Any:
        if inspect.iscoroutinefunction(func):
            return await func(data, context)
        return await anyio.to_thread.run_sync(partial(func, data, context))

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


__all__ = ["AsyncBackend"]
