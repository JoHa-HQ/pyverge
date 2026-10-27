from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any, Generic, TypeAlias

from pyverge.core.context import MigrationContext
from pyverge.core.types import VersionValue
from pyverge.execution.context import ExecutionEnvironment, RunContext
from pyverge.execution.coordinator import ExecutionCoordinator
from pyverge.execution.errors import UnknownModelError
from pyverge.execution.middleware import BackendMiddleware
from pyverge.execution.plan import ExecutionPlan
from pyverge.execution.targets import TargetCompiler, TargetPolicy
from pyverge.execution.types import BackendPort
from pyverge.schemas.types import ModelAdapter

RunResult: TypeAlias = Any


@dataclass(frozen=True, slots=True)
class Runner(Generic[VersionValue]):
    """Coordinate planning and backend execution."""

    coordinator: ExecutionCoordinator[VersionValue]
    adapter: ModelAdapter
    target_compiler: TargetCompiler[VersionValue]
    backend: BackendPort[VersionValue]
    middleware: tuple[BackendMiddleware, ...]
    environment: ExecutionEnvironment

    def plan(
        self,
        payload: dict[str, Any],
        target: TargetPolicy,
        *,
        container: type[Any] | None,
        max_depth: int,
    ) -> ExecutionPlan[VersionValue]:
        resolver = self.target_compiler.compile(target)
        plan = self.coordinator.plan(
            payload,
            resolver,
            container=container,
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
        container: type[Any] | None = None,
        max_depth: int = -1,
        context: MigrationContext | None = None,
        run_id: str | None = None,
    ) -> RunResult:
        plan = self.plan(
            payload,
            target,
            container=container,
            max_depth=max_depth,
        )
        return self.execute(plan, context=context, run_id=run_id)

    def execute(
        self,
        plan: ExecutionPlan[VersionValue],
        *,
        context: MigrationContext | None,
        run_id: str | None = None,
    ) -> RunResult:
        data = copy.deepcopy(plan.payload)
        active_run_id = run_id or self.environment.id_factory.new("run_")
        run = RunContext(
            run_id=active_run_id,
            environment=self.environment,
            bindings=MigrationContext.create(context),
        )
        backend = self.backend
        for layer in reversed(self.middleware):
            backend = layer.wrap(backend)
        return backend.execute(plan, data, run, self.adapter)


__all__ = ["RunResult", "Runner"]
