"""Manager runtime facade."""

from __future__ import annotations

from functools import singledispatchmethod
from typing import TYPE_CHECKING, Generic, Literal, cast

from pyverge.core.clock import SystemClock
from pyverge.core.ids import UuidIdFactory
from pyverge.core.types import (
    ManagerMigrationKey,
    MigrationDirectionStrategy,
    ModelData,
    ModelKey,
    ModelKind,
    ModelPair,
    VersionValue,
)
from pyverge.execution import (
    AnyDirection,
    BackwardDirection,
    ForwardDirection,
    Runner,
    ThreadedBackend,
)
from pyverge.execution.context import ExecutionEnvironment
from pyverge.execution.direction import DirectionPolicy
from pyverge.execution.middleware import BackendMiddleware
from pyverge.execution.types import BackendPort
from pyverge.versioning import Diffable

if TYPE_CHECKING:
    from pyverge.engine import Engine
    from pyverge.manager.manager import Manager


def _direction(strategy: MigrationDirectionStrategy) -> DirectionPolicy:
    policies: dict[MigrationDirectionStrategy, type[DirectionPolicy]] = {
        "any": AnyDirection,
        "forward": ForwardDirection,
        "backward": BackwardDirection,
    }
    return policies[strategy]()


class RuntimeMixin(Generic[VersionValue]):
    """Manager runtime integration and primitive operations."""

    def runner(  # noqa: PLR0913
        self: Manager[VersionValue],
        *,
        backend: BackendPort | None = None,
        middleware: tuple[BackendMiddleware, ...] = (),
        environment: ExecutionEnvironment | None = None,
        runtime: BackendPort | None = None,
        direction: MigrationDirectionStrategy = "any",
        on_direction_violation: str = "skip",
        on_missing_path: str = "raise",
        depth_limit: int = -1,
        on_depth_violation: str = "skip",
        validation_mode: Literal["strict", "lax", "none"] = "lax",
    ) -> Runner[VersionValue]:
        """Build a runtime runner for this manager."""
        return self.engine.runner(
            backend=backend or runtime or ThreadedBackend(max_workers=0),
            middleware=middleware,
            environment=environment
            or ExecutionEnvironment(
                clock=SystemClock(),
                id_factory=UuidIdFactory(),
                logger=None,
                tracer=None,
            ),
            direction=_direction(direction),
            on_direction_violation=on_direction_violation,
            on_missing_path=on_missing_path,
            depth_limit=depth_limit,
            on_depth_violation=on_depth_violation,
            validation_mode=validation_mode,
        )

    def info(
        self: Manager[VersionValue],
    ) -> dict[str, str | int | dict[str, str | int]]:
        """Return manager metadata."""
        engine = self.engine
        return {
            "adapter": type(engine.adapter).__name__,
            "registry": {
                "name": engine.registry.name,
                "models": len(engine.registry.versions),
                "migrations": len(engine.registry.kinds),
            },
        }

    def validate(
        self: Manager[VersionValue],
        data: ModelData,
        kind: ModelKind,
        version: str,
    ) -> None:
        """Validate *data* against ``kind``@``version``.

        Raises :class:`ValidationError` when the payload is invalid.
        """
        versionable = self.get(kind, version, engine=self.engine)
        self.engine.adapter.validate(data, versionable.model)

    @singledispatchmethod
    @classmethod
    def diff(
        cls: type[Manager[VersionValue]],
        key: ModelPair | ManagerMigrationKey,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Diffable[VersionValue]:
        """Build a diff between two model classes or two versions of a kind."""
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
