from __future__ import annotations

import inspect
import time
from collections.abc import Callable, Mapping
from contextlib import AsyncExitStack, ExitStack
from dataclasses import dataclass
from typing import Any, Generic, cast

from pyverge.core.graph.planning.path import Path
from pyverge.core.graph.planning.plan import ExtractedEntry, PathPlan, PathPlanEntry
from pyverge.core.types import MigrationFunc, ModelData, VersionValue
from pyverge.core.versioning import MigrationDescriptor, VersionNode
from pyverge.core.versioning.errors import MigrationApplicationError

from .context import MigrationContext, StepContext
from .errors import AsyncExecutionRequired
from .migrations import HookBinding, MigrationBinding
from .telemetry import StepCompleted, StepFailed, StepStarted


@dataclass(frozen=True, slots=True)
class EntryResult:
    """Migrated value for one payload entry."""

    path: tuple[str | int, ...]
    value: dict[str, Any]


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

    def step_name(self, index: int) -> str:
        return self.migrations[index].name

    def step_context(
        self,
        index: int,
        *,
        run: Any,
        bindings: MigrationContext | None = None,
    ) -> StepContext:
        source, target = self.steps[index]
        return StepContext(
            run=run,
            path=self.path,
            index=index,
            source=source,
            target=target,
            edge=self.plan.edges[index],
            bindings=bindings or MigrationContext.empty(),
            name=self.step_name(index),
            migration=self.migrations[index].descriptor,
        )

    def execute_sync(
        self,
        value: dict[str, Any],
        *,
        run: Any,
        adapter: Any,
        hook_state: Any,
        invoke: Callable[
            [MigrationFunc, ModelData, Mapping[str, object]],
            ModelData,
        ],
    ) -> EntryResult:
        current = value
        for index in range(len(self.steps)):
            step = self.step_context(index, run=run)
            current = self.step(index).run_sync(
                current,
                step,
                hook_state=hook_state,
                invoke=lambda: invoke(
                    self.migration_func(index),
                    current,
                    step.view,
                ),
            )
            if isinstance(current, dict):
                current[adapter.version_property] = str(step.target.version)
        return EntryResult(path=self.path, value=current)

    async def execute_async(
        self,
        value: dict[str, Any],
        *,
        run: Any,
        adapter: Any,
        hook_state: Any,
        invoke: Callable[
            [MigrationFunc, ModelData, Mapping[str, object]],
            Any,
        ],
    ) -> EntryResult:
        current = value
        for index in range(len(self.steps)):
            step = self.step_context(index, run=run)
            current = await self.step(index).run_async(
                current,
                step,
                hook_state=hook_state,
                invoke=lambda: invoke(
                    self.migration_func(index),
                    current,
                    step.view,
                ),
            )
            if isinstance(current, dict):
                current[adapter.version_property] = str(step.target.version)
        return EntryResult(path=self.path, value=current)

    def __call__(
        self,
        index: int,
        data: ModelData,
        context: object | None = None,
    ) -> ModelData:
        return self.invoke_migration(index, data, context)

    def migration_error(self, exc: Exception) -> MigrationApplicationError:
        return MigrationApplicationError(
            self.source.kind,
            self.source,
            self.target,
            f"Failed to apply migration {self.source}->{self.target}: {exc}",
        )

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
            raise self.migration_error(exc) from exc

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
            raise self.migration_error(exc) from exc

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

    def before(
        self,
        data: ModelData,
        step: StepContext,
        hook_state: Any,
        stack: ExitStack,
    ) -> None:
        for result in self.entry.invoke_hook(
            self.index,
            "before_migrate",
            step,
            data,
            state=hook_state,
        ):
            self._raise_on_awaitable(result, "async hook requires async backend")
            if hasattr(result, "__aenter__"):
                raise AsyncExecutionRequired("async hook scope requires async backend")
            if result is not None:
                stack.enter_context(result)

    async def before_async(
        self,
        data: ModelData,
        step: StepContext,
        hook_state: Any,
        stack: AsyncExitStack,
    ) -> None:
        for result in self.entry.invoke_hook(
            self.index,
            "before_migrate",
            step,
            data,
            state=hook_state,
        ):
            resolved = await result if inspect.isawaitable(result) else result
            if resolved is None:
                continue
            if hasattr(resolved, "__aenter__"):
                await stack.enter_async_context(cast("Any", resolved))
            else:
                stack.enter_context(resolved)

    def after(
        self,
        data: ModelData,
        migrated: ModelData,
        step: StepContext,
        hook_state: Any,
    ) -> None:
        for result in self.entry.invoke_hook(
            self.index,
            "after_migrate",
            step,
            data,
            migrated,
            state=hook_state,
        ):
            self._raise_on_awaitable(result, "async hook requires async backend")

    async def after_async(
        self,
        data: ModelData,
        migrated: ModelData,
        step: StepContext,
        hook_state: Any,
    ) -> None:
        for result in self.entry.invoke_hook(
            self.index,
            "after_migrate",
            step,
            data,
            migrated,
            state=hook_state,
        ):
            if inspect.isawaitable(result):
                await result

    def on_error(
        self,
        data: ModelData,
        error: Exception,
        step: StepContext,
        hook_state: Any,
    ) -> None:
        for result in self.entry.invoke_hook(
            self.index,
            "on_error",
            step,
            data,
            error,
            state=hook_state,
        ):
            self._raise_on_awaitable(result, "async hook requires async backend")

    async def on_error_async(
        self,
        data: ModelData,
        error: Exception,
        step: StepContext,
        hook_state: Any,
    ) -> None:
        for result in self.entry.invoke_hook(
            self.index,
            "on_error",
            step,
            data,
            error,
            state=hook_state,
        ):
            if inspect.isawaitable(result):
                await result

    def run_sync(
        self,
        data: ModelData,
        step: StepContext,
        *,
        hook_state: Any,
        invoke: Callable[[], ModelData] | None = None,
    ) -> ModelData:
        telemetry = step.run.environment.telemetry
        started = time.perf_counter()
        if telemetry.emits_success:
            telemetry.emit(StepStarted(step=step))
        try:
            with ExitStack() as stack:
                self.before(data, step, hook_state, stack)
                try:
                    migrated = (
                        invoke()
                        if invoke is not None
                        else self.entry.invoke_migration(self.index, data, step.view)
                    )
                    self._raise_on_awaitable(
                        migrated, "coroutine migration requires async backend"
                    )
                except Exception as error:
                    self.on_error(data, error, step, hook_state)
                    if isinstance(
                        error, (AsyncExecutionRequired, MigrationApplicationError)
                    ):
                        raise
                    raise self.entry.migration_error(error) from error
                self.after(data, migrated, step, hook_state)
        except BaseException as error:
            if telemetry.emits_failure:
                telemetry.emit(
                    StepFailed(
                        step=step,
                        error=error,
                        duration_seconds=time.perf_counter() - started,
                    )
                )
            raise
        if telemetry.emits_success:
            telemetry.emit(
                StepCompleted(
                    step=step,
                    duration_seconds=time.perf_counter() - started,
                )
            )
        return migrated

    async def run_async(
        self,
        data: ModelData,
        step: StepContext,
        *,
        hook_state: Any,
        invoke: Callable[[], Any] | None = None,
    ) -> ModelData:
        telemetry = step.run.environment.telemetry
        started = time.perf_counter()
        if telemetry.emits_success:
            telemetry.emit(StepStarted(step=step))
        try:
            async with AsyncExitStack() as stack:
                await self.before_async(data, step, hook_state, stack)
                try:
                    migrated = (
                        await invoke()
                        if invoke is not None
                        else await self.entry.invoke_migration_async(
                            self.index, data, step.view
                        )
                    )
                except Exception as error:
                    await self.on_error_async(data, error, step, hook_state)
                    if isinstance(
                        error, (AsyncExecutionRequired, MigrationApplicationError)
                    ):
                        raise
                    raise self.entry.migration_error(error) from error
                await self.after_async(data, migrated, step, hook_state)
        except BaseException as error:
            if telemetry.emits_failure:
                telemetry.emit(
                    StepFailed(
                        step=step,
                        error=error,
                        duration_seconds=time.perf_counter() - started,
                    )
                )
            raise
        if telemetry.emits_success:
            telemetry.emit(
                StepCompleted(
                    step=step,
                    duration_seconds=time.perf_counter() - started,
                )
            )
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

    def entry_value(
        self,
        payload: dict[str, Any],
        entry: ExecutionEntry[VersionValue],
    ) -> dict[str, Any]:
        return Path(*entry.path).get(payload)

    def apply_results(
        self,
        payload: dict[str, Any],
        results: tuple[EntryResult, ...],
    ) -> dict[str, Any]:
        updated = payload
        for result in results:
            updated = _replace_at(updated, result.path, result.value)
        return updated


def _replace_at(
    value: Any,
    path: tuple[str | int, ...],
    replacement: Any,
) -> Any:
    if not path:
        return replacement
    head, *tail = path
    if isinstance(value, list):
        if not isinstance(head, int):
            raise TypeError(f"List path requires an integer index, got {head!r}")
        clone = list(value)
        clone[head] = _replace_at(value[head], tuple(tail), replacement)
        return clone
    if not isinstance(head, str):
        raise TypeError(f"Mapping path requires a string key, got {head!r}")
    clone = dict(value)
    clone[head] = _replace_at(value[head], tuple(tail), replacement)
    return clone


__all__ = [
    "ExecutionEntry",
    "ExecutionPlan",
    "ExtractedEntry",
    "StepInvoker",
]
