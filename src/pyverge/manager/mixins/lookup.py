from __future__ import annotations

from functools import singledispatchmethod
from typing import TYPE_CHECKING, Any, Generic, cast

from pyverge.core.types import (
    MIGRATION_PAIR_LEN,
    VersionValue,
)
from pyverge.registry.errors import (
    CatalogError,
    MigrationPathError,
    ModelNotFoundError,
)
from pyverge.versioning import (
    Comparable,
    EdgeKey,
    Migratable,
    Transitional,
    VersionEdge,
    VersionKey,
    VersionNode,
)
from pyverge.versioning.errors import MigrationApplicationError

if TYPE_CHECKING:
    from pyverge.engine import Engine
    from pyverge.manager.manager import Manager


class LookupMixin(Generic[VersionValue]):
    """Fluent lookup sugar over the engine's typed registry surface.

    Users may pass raw ``(kind, version)`` model keys, ``(source, target)``
    edge pairs, bare model classes, or already-typed version nodes and edges.
    Normalization to typed registry keys lives here — the engine and registry
    stay typed-only, with the manager as the user-facing facade.
    """

    @singledispatchmethod
    @classmethod
    def _resolve_model_key(
        cls: type[Manager[VersionValue]],
        key: Any,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> VersionKey[VersionValue]:
        engine = engine or cls._default_engine
        namespace = getattr(key, "namespace", engine.registry.namespace)
        return VersionKey[VersionValue](
            namespace=namespace,
            kind=key.kind,
            version=key.version,
        )

    @_resolve_model_key.register(tuple)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        key: tuple,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> VersionKey[VersionValue]:
        engine = engine or cls._default_engine
        kind, value = key
        return VersionKey[VersionValue](
            namespace=engine.registry.namespace,
            kind=kind,
            version=value,
        )

    @_resolve_model_key.register(VersionNode)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        key: VersionNode[VersionValue],
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> VersionKey[VersionValue]:
        return VersionKey[VersionValue](
            namespace=key.namespace,
            kind=key.kind,
            version=key.version,
        )

    @_resolve_model_key.register(type)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        key: type,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> VersionKey[VersionValue]:
        engine = engine or cls._default_engine
        if not engine.adapter.identify(key):
            raise ModelNotFoundError(engine.registry.name, key)
        versionable = engine.registry.get_model_by_ref(engine.adapter.ref(key))
        return VersionKey[VersionValue](
            namespace=versionable.namespace,
            kind=versionable.kind,
            version=versionable.version,
        )

    @singledispatchmethod
    @classmethod
    def _normalize_index(
        cls: type[Manager[VersionValue]],
        index: Any,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> Any:
        if isinstance(index, (Comparable, Transitional, EdgeKey, VersionEdge)):
            return index
        engine = engine or cls._default_engine
        raise CatalogError(
            engine.registry.name,
            f"Unsupported index type: {type(index)}",
        )

    @_normalize_index.register(tuple)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        index: tuple,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> VersionKey[VersionValue] | EdgeKey:
        if len(index) == MIGRATION_PAIR_LEN and isinstance(index[0], str):
            return cls._resolve_model_key(index, engine=engine)
        return EdgeKey.from_pair(*index)

    @_normalize_index.register(type)
    @classmethod
    def _(
        cls: type[Manager[VersionValue]],
        index: type,
        *,
        engine: Engine[VersionValue] | None = None,
    ) -> VersionKey[VersionValue]:
        return cls._resolve_model_key(index, engine=engine)

    def __contains__(self: Manager[VersionValue], index: Any) -> bool:
        engine = self.engine
        if isinstance(index, slice):
            try:
                from_v = engine.get_model(
                    type(self)._resolve_model_key(index.start, engine=engine)
                )
                to_v = engine.get_model(
                    type(self)._resolve_model_key(index.stop, engine=engine)
                )
                engine.find_migration_path(from_v, to_v)
                return True
            except (
                CatalogError,
                MigrationApplicationError,
                MigrationPathError,
                ModelNotFoundError,
                TypeError,
            ):
                return False

        try:
            return type(self)._normalize_index(index, engine=engine) in engine.registry
        except (
            CatalogError,
            MigrationApplicationError,
            MigrationPathError,
            ModelNotFoundError,
            TypeError,
        ):
            return False

    def __getitem__(
        self: Manager[VersionValue], index: Any
    ) -> VersionNode[VersionValue] | Migratable | list[Migratable]:
        engine = self.engine
        if isinstance(index, slice):
            from_v = engine.get_model(
                type(self)._resolve_model_key(index.start, engine=engine)
            )
            to_v = engine.get_model(
                type(self)._resolve_model_key(index.stop, engine=engine)
            )
            path = engine.find_migration_path(from_v, to_v)
            return [
                engine.registry.get_migration_by_edge(EdgeKey.from_pair(src, dst))
                for src, dst in path
            ]
        return cast(
            "VersionNode[VersionValue] | Migratable | list[Migratable]",
            engine.registry[type(self)._normalize_index(index, engine=engine)],
        )

    def migration_path(
        self: Manager[VersionValue],
        from_version: Any,
        to_version: Any,
    ) -> list[tuple[VersionNode[VersionValue], VersionNode[VersionValue]]]:
        engine = self.engine
        return engine.find_migration_path(
            engine.get_model(
                type(self)._resolve_model_key(from_version, engine=engine)
            ),
            engine.get_model(type(self)._resolve_model_key(to_version, engine=engine)),
        )
