from __future__ import annotations

import warnings
from functools import singledispatchmethod
from typing import TYPE_CHECKING, Generic, Literal, cast

from pyverge.core.graph import (
    AnyDirection,
    BackwardDirection,
    DirectionPolicy,
    ForwardDirection,
)
from pyverge.core.ids import UuidIdFactory
from pyverge.core.registry import HealthFailLevel, HealthIssue
from pyverge.core.types import (
    DepthViolationStrategy,
    DirectionViolationStrategy,
    ManagerMigrationKey,
    MigrationDirectionStrategy,
    ModelData,
    ModelKey,
    ModelKind,
    ModelPair,
    VersionMissingStrategy,
    VersionValue,
)
from pyverge.core.versioning import Diffable, Identifiable
from pyverge.runtime import Runner, ThreadedBackend
from pyverge.runtime.clock import SystemClock
from pyverge.runtime.context import DEFAULT_LOGGER, ExecutionEnvironment
from pyverge.runtime.facade import Runtime
from pyverge.runtime.factory import RunnerOptions
from pyverge.runtime.middleware import BackendMiddleware
from pyverge.runtime.types import BackendPort

from ..descriptors import hybridmethod

if TYPE_CHECKING:
    from pyverge.core.engine import Engine
    from pyverge.runtime.manager.manager import Manager


def _direction(strategy: MigrationDirectionStrategy) -> DirectionPolicy:
    policies: dict[MigrationDirectionStrategy, type[DirectionPolicy]] = {
        "any": AnyDirection,
        "forward": ForwardDirection,
        "backward": BackwardDirection,
    }
    return policies[strategy]()


class RuntimeMixin(Generic[VersionValue]):
    """Manager runtime integration and primitive operations."""

    def runtime(  # noqa: PLR0913
        self: Manager[VersionValue],
        *,
        backend: BackendPort | None = None,
        middleware: tuple[BackendMiddleware, ...] = (),
        environment: ExecutionEnvironment | None = None,
        runtime: BackendPort | None = None,
        direction: MigrationDirectionStrategy = "any",
        on_direction_violation: DirectionViolationStrategy = "skip",
        on_missing_path: VersionMissingStrategy = "raise",
        depth_limit: int = -1,
        on_depth_violation: DepthViolationStrategy = "skip",
        validation_mode: Literal["strict", "lax", "none"] = "lax",
    ) -> Runtime[VersionValue]:
        options = RunnerOptions(
            backend=backend or runtime or ThreadedBackend(max_workers=0),
            environment=environment
            or ExecutionEnvironment(
                clock=SystemClock(),
                id_factory=UuidIdFactory(),
                logger=DEFAULT_LOGGER,
                tracer=None,
            ),
            direction=_direction(direction),
            on_direction_violation=on_direction_violation,
            on_missing_path=on_missing_path,
            depth_limit=depth_limit,
            on_depth_violation=on_depth_violation,
            validation_mode=validation_mode,
            middleware=middleware,
        )
        store = type(self)._default_runtime
        return Runtime(engine=self.engine, bindings=store.bindings).with_runner(options)

    def runner(  # noqa: PLR0913
        self: Manager[VersionValue],
        *,
        backend: BackendPort | None = None,
        middleware: tuple[BackendMiddleware, ...] = (),
        environment: ExecutionEnvironment | None = None,
        runtime: BackendPort | None = None,
        direction: MigrationDirectionStrategy = "any",
        on_direction_violation: DirectionViolationStrategy = "skip",
        on_missing_path: VersionMissingStrategy = "raise",
        depth_limit: int = -1,
        on_depth_violation: DepthViolationStrategy = "skip",
        validation_mode: Literal["strict", "lax", "none"] = "lax",
    ) -> Runner[VersionValue]:
        warnings.warn(
            "Manager.runner() is deprecated; use Manager.runtime().runner",
            DeprecationWarning,
            stacklevel=2,
        )
        runtime_view = self.runtime(
            backend=backend,
            middleware=middleware,
            environment=environment,
            runtime=runtime,
            direction=direction,
            on_direction_violation=on_direction_violation,
            on_missing_path=on_missing_path,
            depth_limit=depth_limit,
            on_depth_violation=on_depth_violation,
            validation_mode=validation_mode,
        )
        assert runtime_view.runner is not None
        return runtime_view.runner

    def info(
        self: Manager[VersionValue],
    ) -> dict[str, str | int | dict[str, str | int]]:
        engine = self.engine
        return {
            "adapter": type(engine.adapter).__name__,
            "registry": {
                "namespace": engine.namespace,
                "models": engine.model_count,
                "migrations": engine.migration_count,
            },
        }

    def validate(
        self: Manager[VersionValue],
        data: ModelData,
        kind: ModelKind,
        version: str,
    ) -> None:
        versionable = self.get(kind, version, engine=self.engine)
        self.engine.adapter.validate(
            data, self.engine.adapter.resolve(versionable.descriptor.ref)
        )

    def health(
        self: Manager[VersionValue],
        entity: Identifiable | None = None,
        *,
        fail_level: HealthFailLevel | None = None,
    ) -> tuple[HealthIssue, ...]:
        """Return registry health, optionally raising at a severity threshold.

        Args:
            entity: Node or edge identity to inspect. ``None`` inspects every
                cached entity.
            fail_level: When set, raise when an issue meets or exceeds this
                severity. ``"never"`` disables the check.

        Returns:
            tuple[HealthIssue, ...]: Health issues for the entity or registry.
        """
        return self.engine.health(entity, fail_level=fail_level)

    @hybridmethod
    @singledispatchmethod
    @classmethod
    def diff(
        cls: type[Manager[VersionValue]],
        key: ModelPair | ManagerMigrationKey,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Diffable[VersionValue]:
        raise TypeError(f"Unsupported diff key: {key!r}")

    @diff.register(ModelPair)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        key: ModelPair,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Diffable[VersionValue]:
        engine = engine or cls._default_engine
        source = cls.get_model(key.source, engine=engine)
        target = cls.get_model(key.target, engine=engine)
        return engine.adapter.diff(source, target)

    @diff.register(ManagerMigrationKey)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        key: ManagerMigrationKey,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Diffable[VersionValue]:
        engine = engine or cls._default_engine
        # ``get_model`` parses the version string through the adapter, so pass
        # the raw values through to avoid parsing them a second time.
        source = cls.get_model(
            ModelKey(key.kind, cast(VersionValue, key.source_version)),
            engine=engine,
        )
        target = cls.get_model(
            ModelKey(key.kind, cast(VersionValue, key.target_version)),
            engine=engine,
        )
        return engine.adapter.diff(source, target)
