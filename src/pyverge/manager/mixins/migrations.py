from __future__ import annotations

from functools import singledispatchmethod
from typing import TYPE_CHECKING, Generic, cast

from pyverge.core.types import (
    Attachable,
    ManagerMigrationKey,
    MigrationFunc,
    MigrationKeyInput,
    ModelPair,
    VersionValue,
)
from pyverge.discovery import MigrationSpec, RegisterMigration
from pyverge.providers import JsonataMigration, JsonPatchMigration
from pyverge.versioning import EdgeKey, Migratable

from ..descriptors import hybridmethod

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pyverge.engine import Engine
    from pyverge.manager.manager import Manager


class MigrationStoreMixin(Generic[VersionValue]):
    """Store, fetch and remove migrations, and attach hooks."""

    @singledispatchmethod
    @classmethod
    def _resolve_migration(
        cls: type[Manager[VersionValue]],
        func: MigrationFunc | JsonPatchMigration | JsonataMigration,
    ) -> MigrationFunc:
        return cast(MigrationFunc, func)

    @_resolve_migration.register(JsonPatchMigration)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        func: JsonPatchMigration,
    ) -> MigrationFunc:
        return func.patch

    @_resolve_migration.register(JsonataMigration)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        func: JsonataMigration,
    ) -> MigrationFunc:
        return func.migration

    @hybridmethod
    @singledispatchmethod
    @classmethod
    def store_migration(
        cls: type[Manager[VersionValue]],
        key: MigrationKeyInput,
        func: MigrationFunc | JsonPatchMigration | JsonataMigration,
        *,
        engine: Engine[VersionValue] | None = None,
        backward_compatible: bool = False,
        migration_id: str | None = None,
    ) -> MigrationFunc:
        raise TypeError(f"Unsupported migration key: {key!r}")

    @store_migration.register(ModelPair)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        key: ModelPair,
        func: MigrationFunc | JsonPatchMigration | JsonataMigration,
        *,
        engine: Engine[VersionValue] | None = None,
        backward_compatible: bool = False,
        migration_id: str | None = None,
    ) -> MigrationFunc:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (adapter.versionable(key.source), adapter.versionable(key.target))
        func = cls._resolve_migration(func)
        if migration_id is not None:
            setattr(func, "__migration_id__", migration_id)
        return cast(
            MigrationFunc,
            engine.register(
                RegisterMigration(
                    MigrationSpec(
                        pair,
                        func,
                        backward_compatible,
                    )
                )
            ),
        )

    @store_migration.register(ManagerMigrationKey)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        key: ManagerMigrationKey,
        func: MigrationFunc | JsonPatchMigration | JsonataMigration,
        *,
        engine: Engine[VersionValue] | None = None,
        backward_compatible: bool = False,
        migration_id: str | None = None,
    ) -> MigrationFunc:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (
            adapter.version_key(kind=key.kind, version=key.source_version),
            adapter.version_key(kind=key.kind, version=key.target_version),
        )
        func = cls._resolve_migration(func)
        if migration_id is not None:
            setattr(func, "__migration_id__", migration_id)
        return cast(
            MigrationFunc,
            engine.register(
                RegisterMigration(
                    MigrationSpec(
                        pair,
                        func,
                        backward_compatible,
                    )
                )
            ),
        )

    @hybridmethod
    @singledispatchmethod
    @classmethod
    def remove_migration(
        cls: type[Manager[VersionValue]],
        key: MigrationKeyInput,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> None:
        raise TypeError(f"Unsupported migration key: {key!r}")

    @remove_migration.register(ModelPair)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        key: ModelPair,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> None:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (adapter.versionable(key.source), adapter.versionable(key.target))
        engine.remove_migration(EdgeKey.from_pair(*pair))

    @remove_migration.register(ManagerMigrationKey)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        key: ManagerMigrationKey,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> None:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (
            adapter.version_key(kind=key.kind, version=key.source_version),
            adapter.version_key(kind=key.kind, version=key.target_version),
        )
        engine.remove_migration(EdgeKey.from_pair(*pair))

    @hybridmethod
    @singledispatchmethod
    @classmethod
    def get_migration(
        cls: type[Manager[VersionValue]],
        key: MigrationKeyInput,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Migratable[VersionValue]:
        raise TypeError(f"Unsupported migration key: {key!r}")

    @get_migration.register(ModelPair)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        key: ModelPair,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Migratable[VersionValue]:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (adapter.versionable(key.source), adapter.versionable(key.target))
        return engine.get_migration(EdgeKey.from_pair(*pair))

    @get_migration.register(ManagerMigrationKey)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        key: ManagerMigrationKey,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Migratable[VersionValue]:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (
            adapter.version_key(kind=key.kind, version=key.source_version),
            adapter.version_key(kind=key.kind, version=key.target_version),
        )
        return engine.get_migration(EdgeKey.from_pair(*pair))

    @hybridmethod
    @singledispatchmethod
    @classmethod
    def add_hook(
        cls: type[Manager[VersionValue]],
        key: MigrationKeyInput,
        hook: Attachable,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> None:
        raise TypeError(f"Unsupported migration key: {key!r}")

    @add_hook.register(ModelPair)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        key: ModelPair,
        hook: Attachable,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> None:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (adapter.versionable(key.source), adapter.versionable(key.target))
        engine.add_hook(EdgeKey.from_pair(*pair), hook)

    @add_hook.register(ManagerMigrationKey)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        key: ManagerMigrationKey,
        hook: Attachable,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> None:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (
            adapter.version_key(kind=key.kind, version=key.source_version),
            adapter.version_key(kind=key.kind, version=key.target_version),
        )
        engine.add_hook(EdgeKey.from_pair(*pair), hook)

    @hybridmethod
    @classmethod
    def attach_hooks(
        cls: type[Manager[VersionValue]],
        hooks: Iterable[Attachable],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> None:
        engine = engine or cls._default_engine
        registry = engine.registry
        for kind in registry.kinds:
            for edge in registry.migrations(kind):
                for hook in hooks:
                    registry.add_hook(edge, hook)
