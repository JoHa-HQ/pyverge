from __future__ import annotations

from functools import singledispatchmethod
from typing import TYPE_CHECKING, Generic, cast

from pyverge.core.types import (
    ManagerMigrationKey,
    ModelData,
    ModelKey,
    ModelKind,
    ModelPair,
    VersionValue,
)
from pyverge.versioning import Diffable

if TYPE_CHECKING:
    from pyverge.manager.manager import Manager
    from pyverge.migration.engine import Engine


class MigrateMixin(Generic[VersionValue]):
    """Migrate, validate and diff payloads through the instance engine."""

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
