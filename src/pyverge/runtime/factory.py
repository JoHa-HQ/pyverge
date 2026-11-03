from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pyverge.core.graph import (
    AnyDirection,
    DirectionPolicy,
    MigrationGraph,
    PathFinder,
    PolicyEngine,
    TargetCompiler,
)
from pyverge.core.ids import UuidIdFactory
from pyverge.core.types import (
    DepthViolationStrategy,
    DirectionViolationStrategy,
    VersionMissingStrategy,
    VersionValue,
)
from pyverge.schemas.types import ModelAdapter

from .backends import ThreadedBackend
from .clock import SystemClock
from .context import DEFAULT_LOGGER, ExecutionEnvironment
from .coordinator import ExecutionCoordinator
from .extractors import PayloadWalker
from .middleware import BackendMiddleware
from .migrations import MigrationBindings
from .planner import ExecutionPlanner
from .runner import Runner
from .types import BackendPort


@dataclass(frozen=True, slots=True)
class RunnerOptions:
    """Runtime settings used to assemble one runner."""

    backend: BackendPort
    environment: ExecutionEnvironment
    direction: DirectionPolicy
    on_direction_violation: DirectionViolationStrategy
    on_missing_path: VersionMissingStrategy
    depth_limit: int
    on_depth_violation: DepthViolationStrategy
    validation_mode: Literal["strict", "lax", "none"]
    middleware: tuple[BackendMiddleware, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class RunnerFactory:
    """Build a runner from a locked graph and runtime bindings."""

    def create(  # noqa: PLR0913
        self,
        graph: MigrationGraph[VersionValue],
        bindings: MigrationBindings[VersionValue],
        adapter: ModelAdapter,
        *,
        options: RunnerOptions | None = None,
        backend: BackendPort | None = None,
        environment: ExecutionEnvironment | None = None,
        direction: DirectionPolicy | None = None,
        on_direction_violation: DirectionViolationStrategy = "skip",
        on_missing_path: VersionMissingStrategy = "raise",
        depth_limit: int = -1,
        on_depth_violation: DepthViolationStrategy = "skip",
        validation_mode: Literal["strict", "lax", "none"] = "lax",
        middleware: tuple[BackendMiddleware, ...] = (),
    ) -> Runner[VersionValue]:
        resolved = options or RunnerOptions(
            backend=backend or ThreadedBackend(max_workers=0),
            environment=environment
            or ExecutionEnvironment(
                clock=SystemClock(),
                id_factory=UuidIdFactory(),
                logger=DEFAULT_LOGGER,
                tracer=None,
            ),
            direction=direction or AnyDirection(),
            on_direction_violation=on_direction_violation,
            on_missing_path=on_missing_path,
            depth_limit=depth_limit,
            on_depth_violation=on_depth_violation,
            validation_mode=validation_mode,
            middleware=middleware,
        )
        coordinator = ExecutionCoordinator[VersionValue](
            extractor=PayloadWalker[VersionValue](
                graph,
                adapter=adapter,
                validation_mode=resolved.validation_mode,
            ),
            finder=PathFinder[VersionValue](
                graph=graph,
                targets=TargetCompiler[VersionValue](graph, adapter),
                policy=PolicyEngine[VersionValue](
                    direction=resolved.direction,
                    on_direction_violation=resolved.on_direction_violation,
                    on_missing_path=resolved.on_missing_path,
                    depth_limit=resolved.depth_limit,
                    on_depth_violation=resolved.on_depth_violation,
                ),
            ),
            planner=ExecutionPlanner[VersionValue](bindings=bindings),
        )
        return Runner[VersionValue](
            coordinator=coordinator,
            adapter=adapter,
            backend=resolved.backend,
            middleware=resolved.middleware,
            environment=resolved.environment,
        )

__all__ = ["RunnerFactory", "RunnerOptions"]
