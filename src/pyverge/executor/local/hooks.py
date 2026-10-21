import asyncio
import inspect
from collections.abc import Callable, Mapping
from typing import Any

from pyverge.core.types import Attachable, Comparable


class MigrationHook:
    """Base class for migration hooks.

    Hooks are read-only observers that allow you to inject custom behavior
    before, after, or on error during migrations.  Default implementations
    are no-ops — subclass and override only what you need.

    A provider-specific hook lives with its adapter — e.g.
    :class:`~pyverge.adapters.otel.OTELHook` for OpenTelemetry tracing.

    Async executors use the ``a*`` override when present; otherwise the sync
    method runs in a worker thread.
    """

    def before_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: Mapping[str, Any],
    ) -> None: ...

    def after_migrate(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        original_data: Mapping[str, Any],
        migrated_data: Mapping[str, Any],
    ) -> None: ...

    def on_error(
        self,
        name: str,
        from_version: Comparable,
        to_version: Comparable,
        data: Mapping[str, Any],
        error: Exception,
    ) -> None: ...


async def invoke_async_hook(
    hook: Attachable,
    sync_name: str,
    async_name: str,
    *args: Any,
) -> None:
    """Invoke a hook on the async path without blocking the event loop."""
    async_method: Callable[..., Any] | None = getattr(hook, async_name, None)
    if async_method is not None:
        await async_method(*args)
        return

    sync_method: Callable[..., Any] = getattr(hook, sync_name)
    if inspect.iscoroutinefunction(sync_method):
        await sync_method(*args)
        return

    await asyncio.to_thread(sync_method, *args)
