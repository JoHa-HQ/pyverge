"""Local single-step execution: resolve an edge, run hooks, stamp version."""

from __future__ import annotations

from typing import Generic

from pyverge.core.context import MigrationContext
from pyverge.core.exceptions import MigrationError, MigrationNotFoundError
from pyverge.core.types import (
    Attachable,
    ModelData,
    Versionable,
    VersionValue,
)
from pyverge.core.versioning import SentinelEdge
from pyverge.migration.registry import Registry

from .hooks import invoke_async_hook


class StepExecutor(Generic[VersionValue]):
    """Resolve a registry edge and run it with hooks and error wrapping."""

    def __init__(self, registry: Registry[VersionValue]) -> None:
        self._registry = registry

    def execute_step(
        self,
        step_from: Versionable[VersionValue],
        step_to: Versionable[VersionValue],
        data: ModelData,
        hooks: tuple[Attachable, ...],
        vp: str,
        context: MigrationContext | None = None,
    ) -> ModelData:
        """Execute a single migration step and update the version property."""
        edge = self._resolve_edge(step_from, step_to)
        hooks_list = list(hooks)
        try:
            for hook in hooks_list:
                hook.before_migrate(str(step_from.kind), step_from, step_to, data)
            result = edge(data, context)
            for hook in hooks_list:
                hook.after_migrate(
                    str(step_from.kind), step_from, step_to, data, result
                )
        except Exception as exc:
            for hook in hooks_list:
                hook.on_error(str(step_from.kind), step_from, step_to, data, exc)
            if isinstance(exc, MigrationError):
                raise
            raise MigrationError(
                str(step_from.kind),
                step_from,
                step_to,
                f"Migration failed: {type(exc).__name__}: {exc}",
            ) from exc

        result[vp] = str(step_to.version[1])
        return result

    async def aexecute_step(
        self,
        step_from: Versionable[VersionValue],
        step_to: Versionable[VersionValue],
        data: ModelData,
        hooks: tuple[Attachable, ...],
        vp: str,
        context: MigrationContext | None = None,
    ) -> ModelData:
        """Async counterpart of :meth:`execute_step`."""
        edge = self._resolve_edge(step_from, step_to)
        hooks_list = list(hooks)
        try:
            for hook in hooks_list:
                await invoke_async_hook(
                    hook,
                    "before_migrate",
                    "abefore_migrate",
                    str(step_from.kind),
                    step_from,
                    step_to,
                    data,
                )
            result = edge(data, context)
            for hook in hooks_list:
                await invoke_async_hook(
                    hook,
                    "after_migrate",
                    "aafter_migrate",
                    str(step_from.kind),
                    step_from,
                    step_to,
                    data,
                    result,
                )
        except Exception as exc:
            for hook in hooks_list:
                await invoke_async_hook(
                    hook,
                    "on_error",
                    "aon_error",
                    str(step_from.kind),
                    step_from,
                    step_to,
                    data,
                    exc,
                )
            if isinstance(exc, MigrationError):
                raise
            raise MigrationError(
                str(step_from.kind),
                step_from,
                step_to,
                f"Migration failed: {type(exc).__name__}: {exc}",
            ) from exc

        result[vp] = str(step_to.version[1])
        return result

    def _resolve_edge(
        self,
        step_from: Versionable[VersionValue],
        step_to: Versionable[VersionValue],
    ):
        """Resolve a pair of endpoints to a registered migration edge."""
        key = SentinelEdge.from_pair(step_from, step_to)
        if self._registry.has_migration(key):
            return self._registry.get_migration(key)
        raise MigrationNotFoundError(
            self._registry.name,
            (step_from, step_to),
        )
