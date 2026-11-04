from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Generic

from pyverge.core.graph.planning.plan import ExtractedEntry, PathPlan, PathPlanEntry
from pyverge.core.types import ModelData, VersionValue
from pyverge.core.versioning import MigrationDescriptor, VersionNode
from pyverge.core.versioning.errors import MigrationApplicationError

from .errors import AsyncExecutionRequired
from .migrations import HookBinding, MigrationBinding


@dataclass(frozen=True, slots=True)
class ExecutionEntry(Generic[VersionValue]):
    """One core path-plan entry with runtime callables and hooks bound."""

    plan: PathPlanEntry[VersionValue]
    migrations: tuple[MigrationBinding, ...]
    hooks: tuple[tuple[HookBinding, ...], ...]

    @property
    def path(self) -> tuple[str | int, ...]:
        return self.plan.path

    @property
    def source(self) -> VersionNode[VersionValue]:
        return self.plan.source

    @property
    def target(self) -> VersionNode[VersionValue]:
        return self.plan.target

    @property
    def steps(
        self,
    ) -> tuple[tuple[VersionNode[VersionValue], VersionNode[VersionValue]], ...]:
        return self.plan.steps

    @property
    def migration_descriptors(self) -> tuple[MigrationDescriptor, ...]:
        return tuple(binding.descriptor for binding in self.migrations)

    def __call__(
        self,
        index: int,
        data: ModelData,
        context: object | None = None,
    ) -> ModelData:
        return self.invoke_migration(index, data, context)

    def invoke_migration(
        self,
        index: int,
        data: ModelData,
        context: object | None = None,
    ) -> ModelData:
        binding = self.migrations[index]
        try:
            return binding.func(data, context)
        except Exception as exc:
            raise MigrationApplicationError(
                self.source.kind,
                self.source,
                self.target,
                f"Failed to apply migration {self.source}->{self.target}: {exc}",
            ) from exc

    def step(self, index: int) -> StepInvoker[VersionValue]:
        return StepInvoker(self, index)

    def migration_func(self, index: int) -> Any:
        return self.migrations[index].func

    async def invoke_migration_async(
        self,
        index: int,
        data: ModelData,
        context: object | None = None,
    ) -> ModelData:
        binding = self.migrations[index]
        try:
            result = binding.func(data, context)
            if inspect.isawaitable(result):
                return await result
            return result
        except Exception as exc:
            raise MigrationApplicationError(
                self.source.kind,
                self.source,
                self.target,
                f"Failed to apply migration {self.source}->{self.target}: {exc}",
            ) from exc

    def invoke_hook(
        self,
        index: int,
        phase: str,
        *args: Any,
        **kwargs: Any,
    ) -> tuple[Any, ...]:
        return tuple(
            getattr(binding.hook, phase)(*args, **kwargs)
            for binding in self.hooks[index]
        )


@dataclass(frozen=True, slots=True)
class StepInvoker(Generic[VersionValue]):
    """Callable step lifecycle owned by one execution entry."""

    entry: ExecutionEntry[VersionValue]
    index: int

    @property
    def migration(self) -> MigrationDescriptor | None:
        descriptors = self.entry.migration_descriptors
        if self.index < len(descriptors):
            return descriptors[self.index]
        return None

    def before(self, data: ModelData, name: str, hook_state: Any) -> None:
        for result in self.entry.invoke_hook(
            self.index,
            "before_migrate",
            name,
            self.entry.source,
            self.entry.target,
            data,
            migration=self.migration,
            state=hook_state,
        ):
            self._raise_on_awaitable(result, "async hook requires async backend")

    async def before_async(self, data: ModelData, name: str, hook_state: Any) -> None:
        for result in self.entry.invoke_hook(
            self.index,
            "before_migrate",
            name,
            self.entry.source,
            self.entry.target,
            data,
            migration=self.migration,
            state=hook_state,
        ):
            if inspect.isawaitable(result):
                await result

    def after(
        self,
        data: ModelData,
        migrated: ModelData,
        name: str,
        hook_state: Any,
    ) -> None:
        for result in self.entry.invoke_hook(
            self.index,
            "after_migrate",
            name,
            self.entry.source,
            self.entry.target,
            data,
            migrated,
            migration=self.migration,
            state=hook_state,
        ):
            self._raise_on_awaitable(result, "async hook requires async backend")

    async def after_async(
        self,
        data: ModelData,
        migrated: ModelData,
        name: str,
        hook_state: Any,
    ) -> None:
        for result in self.entry.invoke_hook(
            self.index,
            "after_migrate",
            name,
            self.entry.source,
            self.entry.target,
            data,
            migrated,
            migration=self.migration,
            state=hook_state,
        ):
            if inspect.isawaitable(result):
                await result

    def on_error(
        self,
        data: ModelData,
        error: Exception,
        name: str,
        hook_state: Any,
    ) -> None:
        for result in self.entry.invoke_hook(
            self.index,
            "on_error",
            name,
            self.entry.source,
            self.entry.target,
            data,
            error,
            migration=self.migration,
            state=hook_state,
        ):
            self._raise_on_awaitable(result, "async hook requires async backend")

    async def on_error_async(
        self,
        data: ModelData,
        error: Exception,
        name: str,
        hook_state: Any,
    ) -> None:
        for result in self.entry.invoke_hook(
            self.index,
            "on_error",
            name,
            self.entry.source,
            self.entry.target,
            data,
            error,
            migration=self.migration,
            state=hook_state,
        ):
            if inspect.isawaitable(result):
                await result

    def run_sync(
        self,
        data: ModelData,
        context: object | None,
        *,
        name: str,
        hook_state: Any,
    ) -> ModelData:
        self.before(data, name, hook_state)
        try:
            migrated = self.entry.invoke_migration(self.index, data, context)
            self._raise_on_awaitable(
                migrated, "coroutine migration requires async backend"
            )
        except Exception as error:
            self.on_error(data, error, name, hook_state)
            raise
        self.after(data, migrated, name, hook_state)
        return migrated

    async def run_async(
        self,
        data: ModelData,
        context: object | None,
        *,
        name: str,
        hook_state: Any,
    ) -> ModelData:
        await self.before_async(data, name, hook_state)
        try:
            migrated = await self.entry.invoke_migration_async(
                self.index, data, context
            )
        except Exception as error:
            await self.on_error_async(data, error, name, hook_state)
            raise
        await self.after_async(data, migrated, name, hook_state)
        return migrated

    @staticmethod
    def _raise_on_awaitable(result: Any, message: str) -> None:
        if inspect.isawaitable(result):
            if inspect.iscoroutine(result):
                result.close()
            raise AsyncExecutionRequired(message)


@dataclass(frozen=True, slots=True)
class ExecutionPlan(Generic[VersionValue]):
    """Runtime-bound execution plan produced from a PathPlan."""

    path: PathPlan[VersionValue]
    payload: dict[str, Any]
    levels: tuple[tuple[ExecutionEntry[VersionValue], ...], ...]


__all__ = [
    "ExecutionEntry",
    "ExecutionPlan",
    "ExtractedEntry",
    "StepInvoker",
]
