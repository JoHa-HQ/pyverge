from __future__ import annotations

from functools import singledispatchmethod
from typing import TYPE_CHECKING, Generic, cast

from pyverge.core.types import (
    Attachable,
    ManagerMigrationKey,
    Migratable,
    MigrationFunc,
    MigrationKeyInput,
    ModelPair,
    VersionValue,
)
from pyverge.core.versioning import (
    SentinelEdge,
)
from pyverge.providers import JsonataMigration, JsonPatchMigration

if TYPE_CHECKING:
    from collections.abc import Iterable

    from pyverge.migration.engine import Engine

    from . import ManagerState


class MigrationStoreMixin(Generic[VersionValue]):
    """Store, fetch and remove migrations, and attach hooks."""

    @singledispatchmethod
    @classmethod
    def _resolve_migration(
        cls: type[ManagerState[VersionValue]],
        func: MigrationFunc | JsonPatchMigration | JsonataMigration,
    ) -> MigrationFunc:
        return cast(MigrationFunc, func)

    @_resolve_migration.register(JsonPatchMigration)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        func: JsonPatchMigration,
    ) -> MigrationFunc:
        return func.patch

    @_resolve_migration.register(JsonataMigration)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        func: JsonataMigration,
    ) -> MigrationFunc:
        return func.migration

    @singledispatchmethod
    @classmethod
    def store_migration(
        cls: type[ManagerState[VersionValue]],
        key: MigrationKeyInput,
        func: MigrationFunc | JsonPatchMigration | JsonataMigration,
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
        func: MigrationFunc | JsonPatchMigration | JsonataMigration,
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
        func: MigrationFunc | JsonPatchMigration | JsonataMigration,
        *,
        engine: Engine[VersionValue] | None = None,
        backward_compatible: bool = False,
    ) -> MigrationFunc:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (
            adapter.version_key(kind=key.kind, version=key.source_version),
            adapter.version_key(kind=key.kind, version=key.target_version),
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
            adapter.version_key(kind=key.kind, version=key.source_version),
            adapter.version_key(kind=key.kind, version=key.target_version),
        )
        engine.remove_migration(SentinelEdge.from_pair(*pair))

    @singledispatchmethod
    @classmethod
    def get_migration(
        cls: type[ManagerState[VersionValue]],
        key: MigrationKeyInput,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Migratable[VersionValue]:
        raise TypeError(f"Unsupported migration key: {key!r}")

    @get_migration.register(ModelPair)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: ModelPair,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Migratable[VersionValue]:
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
    ) -> Migratable[VersionValue]:
        engine = engine or cls._default_engine
        adapter = engine.adapter
        pair = (
            adapter.version_key(kind=key.kind, version=key.source_version),
            adapter.version_key(kind=key.kind, version=key.target_version),
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
            adapter.version_key(kind=key.kind, version=key.source_version),
            adapter.version_key(kind=key.kind, version=key.target_version),
        )
        engine.add_hook(SentinelEdge.from_pair(*pair), hook)

    @classmethod
    def attach_hooks(
        cls: type[ManagerState[VersionValue]],
        hooks: Iterable[Attachable],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> None:
        """Attach *hooks* to every registered migration edge.

        The bulk form of :meth:`add_hook`, for observers that watch the whole
        graph (e.g. tracing every step). Callable from the class or an instance;
        pass *engine* to target a specific engine explicitly.
        """
        engine = engine or cls._default_engine
        registry = engine.registry
        for kind in registry.kinds:
            for edge in registry.migrations(kind):
                for hook in hooks:
                    registry.add_hook(edge, hook)
