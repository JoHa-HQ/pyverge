"""Single-step execution: resolve a registry edge and run it with hooks."""

from __future__ import annotations

from typing import Generic

from pyverge.core.context import MigrationContext
from pyverge.core.exceptions import MigrationError, MigrationNotFoundError
from pyverge.core.steps import ExplicitStep, invoke_async_hook
from pyverge.core.types import (
    Attachable,
    ModelData,
    Versionable,
    VersionValue,
)
from pyverge.core.versioning import SentinelEdge
from pyverge.migration.registry import Registry


class StepExecutor(Generic[VersionValue]):
    """Resolves and runs a single migration step from the registry."""

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
        step = self._resolve_step(step_from, step_to)
        hooks_list = list(hooks)
        try:
            result = step.execute(data, hooks_list, context)
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
        step = self._resolve_step(step_from, step_to)
        hooks_list = list(hooks)
        try:
            result = await step.aexecute(data, hooks_list, context)
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

    def _resolve_step(
        self,
        step_from: Versionable[VersionValue],
        step_to: Versionable[VersionValue],
    ) -> ExplicitStep[VersionValue]:
        """Resolve an edge to an explicit migration step."""
        key = SentinelEdge.from_pair(step_from, step_to)
        if self._registry.has_migration(key):
            return ExplicitStep[VersionValue](self._registry.get_migration(key))
        raise MigrationNotFoundError(
            self._registry.name,
            (step_from, step_to),
        )
