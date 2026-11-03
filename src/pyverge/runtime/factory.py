from __future__ import annotations

from dataclasses import dataclass, field, replace
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
from .plan_cache import PlanCache
from .planner import ExecutionPlanner
from .runner import Runner
from .telemetry import TelemetryAdapter, TelemetryPublisher
from .types import BackendPort, CopyPolicy


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
    discriminator: str = "default"
    middleware: tuple[BackendMiddleware, ...] = field(default_factory=tuple)
    telemetry: tuple[TelemetryAdapter, ...] = field(default_factory=tuple)
    plan_cache_size: int = 0
    copy: CopyPolicy = "deep"


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
        discriminator: str = "default",
        middleware: tuple[BackendMiddleware, ...] = (),
        telemetry: tuple[TelemetryAdapter, ...] = (),
        plan_cache_size: int = 0,
        copy: CopyPolicy = "deep",
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
            discriminator=discriminator,
            middleware=middleware,
            telemetry=telemetry,
            plan_cache_size=plan_cache_size,
            copy=copy,
        )
        environment = (
            replace(
                resolved.environment,
                telemetry=TelemetryPublisher(adapters=resolved.telemetry),
            )
            if resolved.telemetry
            else resolved.environment
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
                discriminator=resolved.discriminator,
                policy=PolicyEngine[VersionValue](
                    direction=resolved.direction,
                    on_direction_violation=resolved.on_direction_violation,
                    on_missing_path=resolved.on_missing_path,
                    depth_limit=resolved.depth_limit,
                    on_depth_violation=resolved.on_depth_violation,
                ),
            ),
            planner=ExecutionPlanner[VersionValue](bindings=bindings),
            cache=PlanCache(resolved.plan_cache_size),
        )
        return Runner[VersionValue](
            coordinator=coordinator,
            adapter=adapter,
            backend=resolved.backend,
            middleware=resolved.middleware,
            environment=environment,
            copy=resolved.copy,
        )


__all__ = ["RunnerFactory", "RunnerOptions"]
