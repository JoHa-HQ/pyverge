from __future__ import annotations

import copy
import inspect
import time
from dataclasses import dataclass
from typing import Any, Generic, TypeAlias

from pyverge.core.graph.planning.path import Path
from pyverge.core.graph.planning.targets import TargetPolicy
from pyverge.core.types import VersionValue
from pyverge.runtime.context import ExecutionEnvironment, MigrationContext, RunContext
from pyverge.runtime.coordinator import ExecutionCoordinator
from pyverge.runtime.errors import TargetValidationError, UnknownModelError
from pyverge.runtime.middleware import BackendMiddleware
from pyverge.runtime.plan import ExecutionPlan
from pyverge.runtime.telemetry import RunCompleted, RunFailed, RunStarted
from pyverge.runtime.types import BackendPort, CopyPolicy
from pyverge.schemas.types import ModelAdapter

RunResult: TypeAlias = Any


@dataclass(frozen=True, slots=True)
class Runner(Generic[VersionValue]):
    """Coordinate planning, execution, and target validation."""

    coordinator: ExecutionCoordinator[VersionValue]
    adapter: ModelAdapter
    backend: BackendPort[VersionValue]
    middleware: tuple[BackendMiddleware, ...]
    environment: ExecutionEnvironment
    copy: CopyPolicy = "deep"

    def plan(
        self,
        payload: dict[str, Any],
        target: TargetPolicy,
        *,
        source_model: type[Any] | None = None,
        max_depth: int = -1,
    ) -> ExecutionPlan[VersionValue]:
        plan = self.coordinator.plan(
            payload,
            target,
            source_model=source_model,
            max_depth=max_depth,
        )
        for entry in plan.path.entries:
            if not self.adapter.identify(self.adapter.resolve(entry.target_model)):
                raise UnknownModelError(
                    f"Runner adapter cannot identify {entry.target_model!r}"
                )
        return plan

    def run(  # noqa: PLR0913
        self,
        payload: dict[str, Any],
        target: TargetPolicy,
        *,
        source_model: type[Any] | None = None,
        max_depth: int = -1,
        context: MigrationContext | None = None,
        run_id: str | None = None,
        validate_target: bool = False,
    ) -> RunResult:
        plan = self.plan(
            payload,
            target,
            source_model=source_model,
            max_depth=max_depth,
        )
        data = self.execute(plan, context=context, run_id=run_id)
        if validate_target:
            self._validate_target(plan, data)
        return data

    def execute(
        self,
        plan: ExecutionPlan[VersionValue],
        *,
        context: MigrationContext | None,
        run_id: str | None = None,
    ) -> RunResult:
        data = self._copy(plan.payload)
        active_run_id = run_id or self.environment.id_factory.new("run_")
        run = RunContext(
            run_id=active_run_id,
            namespace=self.coordinator.finder.graph.namespace,
            environment=self.environment,
            bindings=MigrationContext.create(context),
        )
        telemetry = self.environment.telemetry
        if telemetry.emits_success:
            telemetry.emit(RunStarted(run=run, plan=plan))
        started = time.perf_counter()
        try:
            backend = self.backend
            for layer in reversed(self.middleware):
                backend = layer.wrap(backend)
            result = backend.execute(plan, data, run, self.adapter)
        except BaseException as error:
            if telemetry.emits_failure:
                telemetry.emit(
                    RunFailed(
                        run=run,
                        plan=plan,
                        error=error,
                        duration_seconds=time.perf_counter() - started,
                    )
                )
            raise
        if inspect.isawaitable(result):
            return self._await_result(result, run, plan, started)
        if telemetry.emits_success:
            telemetry.emit(
                RunCompleted(
                    run=run,
                    plan=plan,
                    duration_seconds=time.perf_counter() - started,
                )
            )
        return result

    def _copy(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.copy == "none":
            return payload
        if self.copy == "shallow":
            return dict(payload)
        return copy.deepcopy(payload)

    async def _await_result(
        self,
        result: Any,
        run: RunContext,
        plan: ExecutionPlan[VersionValue],
        started: float,
    ) -> Any:
        telemetry = self.environment.telemetry
        try:
            value = await result
        except BaseException as error:
            if telemetry.emits_failure:
                telemetry.emit(
                    RunFailed(
                        run=run,
                        plan=plan,
                        error=error,
                        duration_seconds=time.perf_counter() - started,
                    )
                )
            raise
        if telemetry.emits_success:
            telemetry.emit(
                RunCompleted(
                    run=run,
                    plan=plan,
                    duration_seconds=time.perf_counter() - started,
                )
            )
        return value

    def _validate_target(
        self, plan: ExecutionPlan[VersionValue], data: dict[str, Any]
    ) -> None:
        for entry in plan.path.entries:
            path = Path(*entry.path)
            value = path.get(data)
            if not isinstance(value, dict):
                raise TargetValidationError(
                    path=entry.path,
                    target_model=entry.target_model,
                    error=TypeError("target payload is not a mapping"),
                )
            resolved = self.adapter.resolve(entry.target_model)
            try:
                path.set(data, self.adapter.finalize(resolved, value))
            except Exception as error:
                raise TargetValidationError(
                    path=entry.path,
                    target_model=entry.target_model,
                    error=error,
                ) from error


__all__ = ["RunResult", "Runner"]
