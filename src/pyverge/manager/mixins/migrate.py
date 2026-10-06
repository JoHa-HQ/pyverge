from __future__ import annotations

from functools import singledispatchmethod
from typing import TYPE_CHECKING, Generic, cast, overload

from pyverge.core.types import (
    Diffable,
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
from pyverge.manager.types import (
    TargetPolicy,
)
from pyverge.migration.types import (
    Executor,
    MigrationEntry,
)
from pyverge.providers.types import (
    TContainer,
)

if TYPE_CHECKING:
    from pyverge.migration.engine import Engine

    from . import ManagerState


class MigrateMixin(Generic[VersionValue]):
    """Migrate, validate and diff payloads through the instance engine."""

    @overload
    def migrate(
        self: ManagerState[VersionValue],
        data: ModelData,
        target: TargetPolicy = "latest",
        *,
        container: type[TContainer],
        version_property: str | None = None,
        depth_limit: int | None = None,
        direction: MigrationDirectionStrategy | None = None,
        on_direction_violation: DirectionViolationStrategy | None = None,
        on_version_not_found: VersionMissingStrategy | None = None,
        executor: Executor | None = None,
        entry_migration: MigrationEntry[VersionValue] | None = None,
    ) -> TContainer: ...

    @overload
    def migrate(
        self: ManagerState[VersionValue],
        data: ModelData,
        target: TargetPolicy = "latest",
        *,
        container: None = None,
        version_property: str | None = None,
        depth_limit: int | None = None,
        direction: MigrationDirectionStrategy | None = None,
        on_direction_violation: DirectionViolationStrategy | None = None,
        on_version_not_found: VersionMissingStrategy | None = None,
        executor: Executor | None = None,
        entry_migration: MigrationEntry[VersionValue] | None = None,
    ) -> ModelData: ...

    def migrate(  # noqa: PLR0913
        self: ManagerState[VersionValue],
        data: ModelData,
        target: TargetPolicy = "latest",
        *,
        container: type[TContainer] | None = None,
        version_property: str | None = None,
        depth_limit: int | None = None,
        direction: MigrationDirectionStrategy | None = None,
        on_direction_violation: DirectionViolationStrategy | None = None,
        on_version_not_found: VersionMissingStrategy | None = None,
        executor: Executor | None = None,
        entry_migration: MigrationEntry[VersionValue] | None = None,
    ) -> ModelData | TContainer:
        """Migrate *data* to the configured target policy.

        *target* accepts a declarative spec (string, model class, versionable,
        ``None``/``"skip"``), a per-kind mapping, or an existing callable
        resolver. Defaults to ``"latest"``.

        When *container* is given, the migrated payload is validated against it
        and a typed container instance is returned instead of a dict.
        """
        resolved_target = self._resolve_target_policy(target, engine=self.engine)
        migrated = self.engine.migrate(
            data,
            target=resolved_target,
            container=container,
            version_property=version_property,
            depth_limit=depth_limit,
            direction=direction,
            on_direction_violation=on_direction_violation,
            on_version_not_found=on_version_not_found,
            executor=executor,
            entry_migration=entry_migration,
        )
        if container is None:
            return migrated
        return container.model_validate(migrated)

    def info(
        self: ManagerState[VersionValue],
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
        self: ManagerState[VersionValue],
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
        cls: type[ManagerState[VersionValue]],
        key: ModelPair | ManagerMigrationKey,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Diffable[VersionValue]:
        """Build a diff between two model classes or two versions of a kind."""
        raise TypeError(f"Unsupported diff key: {key!r}")

    @diff.register(ModelPair)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
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
        cls: type[ManagerState[VersionValue]],
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
