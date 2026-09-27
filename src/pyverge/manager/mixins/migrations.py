"""Migration and hook storage slice of the composed manager."""

from __future__ import annotations

from functools import singledispatchmethod
from typing import TYPE_CHECKING, Generic, cast

from pyverge.adapters import JsonPatchMigration
from pyverge.core.versioning import SentinelEdge
from pyverge.types import (
    Attachable,
    ManagerMigrationKey,
    Migratable,
    MigrationFunc,
    MigrationKeyInput,
    ModelPair,
    VersionValue,
    VModel,
)

if TYPE_CHECKING:
    from pyverge.migration.engine import Engine

    from . import ManagerState


class MigrationStoreMixin(Generic[VersionValue]):
    """Store, fetch and remove migrations, and attach hooks."""

    @singledispatchmethod
    @classmethod
    def _resolve_migration(
        cls: type[ManagerState[VersionValue]],
        func: MigrationFunc | JsonPatchMigration,
    ) -> MigrationFunc:
        return cast(MigrationFunc, func)

    @_resolve_migration.register(JsonPatchMigration)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        func: JsonPatchMigration,
    ) -> MigrationFunc:
        return func.patch

    @singledispatchmethod
    @classmethod
    def store_migration(
        cls: type[ManagerState[VersionValue]],
        key: MigrationKeyInput,
        func: MigrationFunc | JsonPatchMigration,
        *,
        engine: Engine[VersionValue] | None = None,
        backward_compatible: bool = False,
    ) -> MigrationFunc:
        raise TypeError(f"Unsupported migration key: {key!r}")

    @store_migration.register(ModelPair)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: ModelPair,
        func: MigrationFunc | JsonPatchMigration,
        *,
        engine: Engine[VersionValue] | None = None,
        backward_compatible: bool = False,
    ) -> MigrationFunc:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (adapter.versionable(key.source), adapter.versionable(key.target))
        return engine.store_migration(
            pair,
            cls._resolve_migration(func),
            backward_compatible=backward_compatible,
        )

    @store_migration.register(ManagerMigrationKey)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: ManagerMigrationKey,
        func: MigrationFunc | JsonPatchMigration,
        *,
        engine: Engine[VersionValue] | None = None,
        backward_compatible: bool = False,
    ) -> MigrationFunc:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (
            adapter.versionable(None, kind=key.kind, version=key.source_version),
            adapter.versionable(None, kind=key.kind, version=key.target_version),
        )
        return engine.store_migration(
            pair,
            cls._resolve_migration(func),
            backward_compatible=backward_compatible,
        )

    @singledispatchmethod
    @classmethod
    def remove_migration(
        cls: type[ManagerState[VersionValue]],
        key: MigrationKeyInput,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> None:
        raise TypeError(f"Unsupported migration key: {key!r}")

    @remove_migration.register(ModelPair)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: ModelPair,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> None:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (adapter.versionable(key.source), adapter.versionable(key.target))
        engine.remove_migration(SentinelEdge.from_pair(*pair))

    @remove_migration.register(ManagerMigrationKey)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: ManagerMigrationKey,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> None:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (
            adapter.versionable(None, kind=key.kind, version=key.source_version),
            adapter.versionable(None, kind=key.kind, version=key.target_version),
        )
        engine.remove_migration(SentinelEdge.from_pair(*pair))

    @singledispatchmethod
    @classmethod
    def get_migration(
        cls: type[ManagerState[VersionValue]],
        key: MigrationKeyInput,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Migratable[VersionValue, VModel, VModel]:
        raise TypeError(f"Unsupported migration key: {key!r}")

    @get_migration.register(ModelPair)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: ModelPair,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Migratable[VersionValue, VModel, VModel]:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (adapter.versionable(key.source), adapter.versionable(key.target))
        return engine.get_migration(SentinelEdge.from_pair(*pair))

    @get_migration.register(ManagerMigrationKey)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: ManagerMigrationKey,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Migratable[VersionValue, VModel, VModel]:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (
            adapter.versionable(None, kind=key.kind, version=key.source_version),
            adapter.versionable(None, kind=key.kind, version=key.target_version),
        )
        return engine.get_migration(SentinelEdge.from_pair(*pair))

    @singledispatchmethod
    @classmethod
    def add_hook(
        cls: type[ManagerState[VersionValue]],
        key: MigrationKeyInput,
        hook: Attachable,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> None:
        raise TypeError(f"Unsupported migration key: {key!r}")

    @add_hook.register(ModelPair)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: ModelPair,
        hook: Attachable,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> None:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (adapter.versionable(key.source), adapter.versionable(key.target))
        engine.add_hook(SentinelEdge.from_pair(*pair), hook)

    @add_hook.register(ManagerMigrationKey)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: ManagerMigrationKey,
        hook: Attachable,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> None:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (
            adapter.versionable(None, kind=key.kind, version=key.source_version),
            adapter.versionable(None, kind=key.kind, version=key.target_version),
        )
        engine.add_hook(SentinelEdge.from_pair(*pair), hook)
