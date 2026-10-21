from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Generic, Protocol

from .context import MigrationContext
from .types import (
    Attachable,
    Migratable,
    ModelData,
    VersionValue,
)


class _Step(Protocol):
    """A single migration step that can be executed."""

    def execute(
        self,
        data: ModelData,
        hooks: list[Attachable],
        context: MigrationContext | None = None,
    ) -> ModelData: ...

    async def aexecute(
        self,
        data: ModelData,
        hooks: list[Attachable],
        context: MigrationContext | None = None,
    ) -> ModelData: ...


async def invoke_async_hook(
    hook: Attachable,
    sync_name: str,
    async_name: str,
    *args: Any,
) -> None:
    """Invoke a hook on the async path without blocking the event loop.

    An overridden async method runs as a coroutine. Otherwise the sync method
    runs in a worker thread via ``asyncio.to_thread``.
    """
    async_method: Callable[..., Any] | None = getattr(hook, async_name, None)
    if async_method is not None:
        await async_method(*args)
        return

    sync_method: Callable[..., Any] = getattr(hook, sync_name)
    if inspect.iscoroutinefunction(sync_method):
        await sync_method(*args)
        return

    await asyncio.to_thread(sync_method, *args)


@dataclass(frozen=True, slots=True)
class ExplicitStep(Generic[VersionValue]):
    """Step backed by a registered :class:`Migratable` edge.

    ``from_version`` / ``to_version`` are derived from the edge itself and
    passed to the hooks — no external endpoints are required.
    """

    edge: Migratable[VersionValue]

    def execute(
        self,
        data: ModelData,
        hooks: list[Attachable],
        context: MigrationContext | None = None,
    ) -> ModelData:
        kind = self.edge.kind
        from_version = self.edge.source
        to_version = self.edge.target
        for hook in hooks:
            hook.before_migrate(str(kind), from_version, to_version, data)
        result = self.edge(data, context)
        for hook in hooks:
            hook.after_migrate(str(kind), from_version, to_version, data, result)
        return result

    async def aexecute(
        self,
        data: ModelData,
        hooks: list[Attachable],
        context: MigrationContext | None = None,
    ) -> ModelData:
        kind = self.edge.kind
        from_version = self.edge.source
        to_version = self.edge.target
        for hook in hooks:
            await invoke_async_hook(
                hook,
                "before_migrate",
                "abefore_migrate",
                str(kind),
                from_version,
                to_version,
                data,
            )
        result = self.edge(data, context)
        for hook in hooks:
            await invoke_async_hook(
                hook,
                "after_migrate",
                "aafter_migrate",
                str(kind),
                from_version,
                to_version,
                data,
                result,
            )
        return result
