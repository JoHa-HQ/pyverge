from __future__ import annotations

from functools import singledispatchmethod
from typing import TYPE_CHECKING, Any, Generic

from pyverge.core.exceptions import (
    MigrationError,
    ModelNotFoundError,
    RegistryError,
)
from pyverge.core.types import (
    MIGRATION_PAIR_LEN,
    Migratable,
    Transitional,
    Versionable,
    VersionValue,
)
from pyverge.core.versioning import (
    SentinelEdge,
    VersionNode,
)

if TYPE_CHECKING:
    from . import ManagerState


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
        cls: type[ManagerState[VersionValue]],
        key: Any,
    ) -> VersionNode[VersionValue]:
        """Normalize a model key to a version node.

        Fallback: any comparable exposing ``kind`` and ``version`` is reduced
        to its ``(kind, version)`` key.
        """
        return VersionNode[VersionValue](
            _model=None, _value=key.version[1], _kind=key.kind
        )

    @_resolve_model_key.register(tuple)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: tuple,
    ) -> VersionNode[VersionValue]:
        kind, value = key
        return VersionNode[VersionValue](_model=None, _value=value, _kind=kind)

    @_resolve_model_key.register(VersionNode)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: VersionNode[VersionValue],
    ) -> VersionNode[VersionValue]:
        return key

    @_resolve_model_key.register(type)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        key: type,
    ) -> VersionNode[VersionValue]:
        """Resolve a bare model class through the adapter and a neutral lookup."""
        engine = cls._default_engine
        if not engine.adapter.identify(key):
            raise ModelNotFoundError(engine.registry.name, key)
        versionable = engine.registry.get_model_by_handle(key)
        return VersionNode[VersionValue](
            _model=None,
            _value=versionable.version[1],
            _kind=versionable.kind,
        )

    @singledispatchmethod
    @classmethod
    def _normalize_index(
        cls: type[ManagerState[VersionValue]],
        index: Any,
    ) -> Any:
        """Map a fluent lookup key to a typed registry key."""
        if isinstance(index, (Versionable, Transitional, SentinelEdge)):
            return index
        raise RegistryError(
            cls._default_engine.registry.name,
            f"Unsupported index type: {type(index)}",
        )

    @_normalize_index.register(tuple)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        index: tuple,
    ) -> VersionNode[VersionValue] | SentinelEdge:
        if len(index) == MIGRATION_PAIR_LEN and isinstance(index[0], str):
            return cls._resolve_model_key(index)
        return SentinelEdge.from_pair(*index)

    @_normalize_index.register(type)
    @classmethod
    def _(
        cls: type[ManagerState[VersionValue]],
        index: type,
    ) -> VersionNode[VersionValue]:
        return cls._resolve_model_key(index)

    def __contains__(self: ManagerState[VersionValue], index: Any) -> bool:
        """Fluent membership: version key, edge pair, model class, or slice."""
        engine = self.engine
        if isinstance(index, slice):
            try:
                from_v = engine.get_model(type(self)._resolve_model_key(index.start))
                to_v = engine.get_model(type(self)._resolve_model_key(index.stop))
                engine.find_migration_path(from_v, to_v)
                return True
            except (MigrationError, ModelNotFoundError, RegistryError, TypeError):
                return False

        try:
            return type(self)._normalize_index(index) in engine.registry
        except (MigrationError, ModelNotFoundError, RegistryError, TypeError):
            return False

    def __getitem__(
        self: ManagerState[VersionValue], index: Any
    ) -> Versionable[VersionValue] | Migratable | list[Migratable]:
        """Fluent selection: a version, an edge, or a migration path (slice)."""
        engine = self.engine
        if isinstance(index, slice):
            from_v = engine.get_model(type(self)._resolve_model_key(index.start))
            to_v = engine.get_model(type(self)._resolve_model_key(index.stop))
            path = engine.find_migration_path(from_v, to_v)
            return [
                engine.registry.get_migration_by_edge(SentinelEdge.from_pair(src, dst))
                for src, dst in path
            ]
        return engine.registry[type(self)._normalize_index(index)]

    def migration_path(
        self: ManagerState[VersionValue],
        from_version: Any,
        to_version: Any,
    ) -> list[tuple[Versionable, Versionable]]:
        """Return the migration chain between two fluent keys."""
        engine = self.engine
        return engine.find_migration_path(
            engine.get_model(type(self)._resolve_model_key(from_version)),
            engine.get_model(type(self)._resolve_model_key(to_version)),
        )
