"""Model registry — single source of truth for models, migrations, and hooks."""

import bisect
from collections import defaultdict
from itertools import chain
from typing import Generic, Self, cast

from pydantic import BaseModel

from .exceptions import (
    MigrationAlreadyRegisteredError,
    MigrationNotFoundError,
    ModelAlreadyRegisteredError,
    ModelNotFoundError,
    RegistryError,
)
from .types import (
    Attachable,
    Comparable,
    LookupKey,
    Migratable,
    MigrationFunc,
    ModelKind,
    ProviderBase_co,
    Transitional,
    Versionable,
    VersionValue_co,
    VSource_co,
    VTarget_co,
)
from .versioning import SentinelEdge


class Registry(Generic[VersionValue_co, ProviderBase_co]):
    """Ordered storage for versioned models, migrations, and hooks.

    Parameterized by the version strategy (``VersionValue_co``) and the model
    provider base (``ProviderBase_co``) it stores.  ``ProviderBase_co`` is the
    provider's shared base (e.g. ``pydantic.BaseModel``); the registry
    binds version literals to concrete model classes via ``Versionable``.
    """

    def __init__(self: Self, *, name: str | None = None) -> None:
        """Create a named registry.

        Internal indexes
        ----------------
        ``_by_versions``
            All registered versions in sorted order.  Used for
            bisect-based lookups and range queries.

        ``_by_kinds``
            Versions grouped by model family (kind).  Each value
            is independently sorted.  Used to walk a single kind's
            version chain for path resolution.

        ``_by_models``
            Inverted mapping from Pydantic model class to its
            registered version.  Used for class-keyed lookups.

        ``_backward_compatible``
            Subset of versions explicitly marked as
            backward-compatible; kept sorted for membership tests.

        ``_migration_path``
            Per-kind sorted lists of registered migration edges,
            maintained via ``bisect.insort``.  Each entry is a
            ``(from_version, to_version)`` pair.  Critical edges
            are those whose endpoints are adjacent in the kind's
            version list.

        ``_edges_by_version``
            Inverted index from a version to the set of migration
            edges that reference it as source or target.  Maintained
            on every migration store/remove; used for O(1) integrity
            checks when removing a model version.

        ``_hooks``
            Per-edge lists of observer hooks fired during migration.
        """
        self._name = name or "registry"
        self._by_versions: list[Versionable[VersionValue_co, ProviderBase_co]] = []
        self._by_kinds: dict[
            ModelKind, list[Versionable[VersionValue_co, ProviderBase_co]]
        ] = defaultdict(list)
        self._by_models: dict[
            type[ProviderBase_co], Versionable[VersionValue_co, ProviderBase_co]
        ] = {}
        self._migrations: dict[ModelKind, list[Migratable]] = defaultdict(list)
        self._edges_by_version: dict[Comparable, set[Migratable]] = defaultdict(set)
        self._hooks: dict[Transitional, list[Attachable]] = defaultdict(list)

    def __contains__(self, index: LookupKey) -> bool:
        """Check whether a version, model, or migration is registered."""
        try:
            if isinstance(index, Versionable):
                return self.get_model(index) is not None
            elif isinstance(index, type) and issubclass(index, BaseModel):
                return (
                    self.get_model_by_class(cast(type[ProviderBase_co], index))
                    is not None
                )
            elif isinstance(index, Transitional):
                return self.has_migration(index)
        except (ModelNotFoundError, MigrationNotFoundError):
            return False
        raise RegistryError(self._name, f"Unsupported index type: {type(index)}")

    def __getitem__(
        self, index: LookupKey
    ) -> (
        Versionable[VersionValue_co, ProviderBase_co]
        | Migratable[VersionValue_co, VSource_co, VTarget_co]
    ):
        """Lookup by version, model class, or migration edge."""

        if isinstance(index, Versionable):
            return self.get_model(index)
        elif isinstance(index, type) and issubclass(index, BaseModel):
            return self.get_model_by_class(cast(type[ProviderBase_co], index))
        elif isinstance(index, Transitional):
            return self.get_migration(index)
        raise RegistryError(self._name, f"Unsupported index type: {type(index)}")

    @property
    def versions(self: Self) -> list[Versionable[VersionValue_co, ProviderBase_co]]:
        """Registered versions in ascending order."""
        return self._by_versions

    @property
    def name(self: Self) -> str:
        """Registry name, used in error messages."""
        return self._name

    @property
    def kinds(self: Self) -> list[ModelKind]:
        """All model kinds that have registered migrations."""
        return list(self._migrations.keys())

    @property
    def latest_version(self) -> Versionable[VersionValue_co, ProviderBase_co]:
        """The most recently registered version overall."""
        if not self._by_versions:
            raise RegistryError(self._name, "No versions registered")
        return self._by_versions[-1]

    def is_adjacent(
        self, key: Transitional[VersionValue_co, VSource_co, VTarget_co]
    ) -> bool:
        """True if *key* connects two neighbours in the kind's version list."""
        kind_versions = self._by_kinds[key.kind]
        from_idx = bisect.bisect_left(kind_versions, key.source)
        to_idx = bisect.bisect_left(kind_versions, key.target)
        return abs(from_idx - to_idx) == 1

    def models(self: Self, kind: ModelKind | None) -> frozenset[type[ProviderBase_co]]:
        """Registered Pydantic model classes."""
        if kind is None:
            return frozenset[type[ProviderBase_co]](
                [v.model for v in self._by_models.values()]
            )
        return frozenset[type[ProviderBase_co]](
            [v.model for v in self._by_kinds.get(kind, [])]
        )

    def migrations(self: Self, kind: ModelKind) -> list[Migratable]:
        """Registered migrations for *kind*."""
        return self._migrations.get(kind, [])

    def migrations_of(self: Self, key: Comparable) -> frozenset[Migratable]:
        """Migration edges referencing *key* as source or target.

        O(1) lookup via the inverted index.  ``VersionNode`` and
        ``SentinelNode`` keys are interchangeable — they share hash
        and equality semantics.
        """
        return frozenset(self._edges_by_version.get(key, ()))

    def kind_versions(
        self: Self, kind: ModelKind
    ) -> list[Versionable[VersionValue_co, ProviderBase_co]]:
        """Registered versions for *kind*, ascending.  Empty if unknown."""
        return list(self._by_kinds.get(kind, []))

    def has_model(self: Self, key: Comparable) -> bool:
        """True if a model matching *key* is registered."""
        idx = bisect.bisect_left(self._by_versions, key)
        return idx < len(self._by_versions) and self._by_versions[idx] == key

    def _find_edge(
        self: Self,
        kind: ModelKind,
        pair: tuple[Comparable, Comparable],
    ) -> Migratable:
        """Return the edge exactly matching *pair* for *kind*.

        Uses bisect on the per-kind migration list with a
        key-only :class:`SentinelEdge` lookup key.
        """
        edges = self._migrations.get(kind, [])
        sentinel = SentinelEdge.from_pair(*pair)
        idx = bisect.bisect_left(edges, sentinel)
        if idx < len(edges) and edges[idx].edge == pair:
            return edges[idx]
        raise MigrationNotFoundError(self._name, pair)

    def has_migration(
        self: Self, key: Transitional[VersionValue_co, VSource_co, VTarget_co]
    ) -> bool:
        """True if an edge exactly matching *key* is registered."""
        try:
            self._find_edge(key.kind, key.edge)
            return True
        except MigrationNotFoundError:
            return False

    def get_migration_by_edge(
        self: Self, key: Transitional[VersionValue_co, VSource_co, VTarget_co]
    ) -> Migratable:
        """Return the edge exactly matching *key*."""
        return self._find_edge(key.kind, key.edge)

    def has_hooks(
        self: Self, key: Transitional[VersionValue_co, VSource_co, VTarget_co]
    ) -> bool:
        """True if *key* has registered hooks."""
        return key in self._hooks

    def latest(
        self: Self, kind: ModelKind
    ) -> Versionable[VersionValue_co, ProviderBase_co]:
        """Most recent (highest) registered version for *kind*."""
        if kind not in self._by_kinds:
            raise RegistryError(self._name, "No versions registered")
        return self._by_kinds[kind][-1]

    def earliest(
        self: Self, kind: ModelKind
    ) -> Versionable[VersionValue_co, ProviderBase_co]:
        """Oldest (lowest) registered version for *kind*."""
        if kind not in self._by_kinds:
            raise RegistryError(self._name, "No versions registered")
        return self._by_kinds[kind][0]

    def hooks(self: Self, key: Transitional | None) -> list[Attachable]:
        """Flattened list of all hooks across all migration keys."""
        if key is None:
            return list(chain(*self._hooks.values()))
        return self._hooks[key]

    def copy(
        self: Self, name: str | None = None
    ) -> "Registry[VersionValue_co, ProviderBase_co]":
        """Return an independent shallow copy."""
        new = Registry(name=name)
        new._by_versions = list(self._by_versions)
        new._by_kinds = defaultdict(
            list, {k: list(v) for k, v in self._by_kinds.items()}
        )
        new._by_models = dict(self._by_models)
        new._migrations = defaultdict(
            list, {k: list(v) for k, v in self._migrations.items()}
        )
        new._edges_by_version = defaultdict(
            set, {v: set(s) for v, s in self._edges_by_version.items()}
        )
        new._hooks = defaultdict(list, {k: list(v) for k, v in self._hooks.items()})
        return new

    def store_model(
        self: Self,
        version: Versionable[VersionValue_co, ProviderBase_co],
    ) -> Versionable[VersionValue_co, ProviderBase_co]:
        """Register a model class at *version*."""
        if version in self._by_versions:
            raise ModelAlreadyRegisteredError(
                registry_name=self._name,
                version=version.version,
            )
        self._by_models[version.model] = version
        bisect.insort_left(self._by_versions, version)
        bisect.insort_left(self._by_kinds[version.version[0]], version)
        return version

    def get_model(
        self: Self,
        key: Comparable,
    ) -> Versionable[VersionValue_co, ProviderBase_co]:
        """Return the model matching *key*."""
        idx = bisect.bisect_left(self._by_versions, key)
        if idx < len(self._by_versions) and (model := self._by_versions[idx]) == key:
            return model
        raise ModelNotFoundError(self._name, key.version)

    def get_model_by_class(
        self: Self, cls: type[ProviderBase_co]
    ) -> Versionable[VersionValue_co, ProviderBase_co]:
        """Return the model matching *cls*."""
        if target := self._by_models.get(cls):
            return target
        raise ModelNotFoundError(self._name, cls)

    def remove_model(self: Self, key: Comparable) -> None:
        """Remove a model version.

        Refuses to remove a version still referenced by registered
        migration edges — remove those migrations first.
        """

        version_idx = bisect.bisect_left(self._by_versions, key)
        kind_idx = bisect.bisect_left(self._by_kinds[key.kind], key)
        if (
            version_idx == len(self._by_versions)
            or self._by_versions[version_idx] != key
        ):
            raise RegistryError(self._name, f"Version {key} is not registered")

        affected = self.migrations_of(key)
        if affected:
            pairs = ", ".join(f"{e.source}→{e.target}" for e in sorted(affected))
            raise RegistryError(
                self._name,
                f"Cannot remove version {key}: it is referenced by migrations: {pairs}",
            )

        version = self._by_versions[version_idx]

        del self._by_kinds[key.kind][kind_idx]
        del self._by_models[version.model]
        del self._by_versions[version_idx]

    def remove_model_by_class(self: Self, cls: type[ProviderBase_co]) -> None:
        """Remove a model by its class."""
        if cls not in self._by_models:
            raise ModelNotFoundError(self._name, cls)
        self.remove_model(self._by_models[cls])

    def clear_models(self: Self) -> None:
        """Remove all models from the registry."""
        if self._migrations:
            raise RegistryError(self._name, "Clear migrations first")
        self._by_versions.clear()
        self._by_models.clear()
        self._by_kinds.clear()

    def store_migration(
        self: Self,
        key: Migratable[VersionValue_co, VSource_co, VTarget_co],
    ) -> MigrationFunc:
        """Register a migration function between two versions."""
        if any(v not in self._by_versions for v in key.edge):
            raise MigrationNotFoundError(self._name, key.edge)

        paths = self._migrations.get(key.kind, [])

        if key in paths:
            raise MigrationAlreadyRegisteredError(self._name, key.edge)

        bisect.insort(self._migrations[key.kind], key)
        self._edges_by_version[key.source].add(key)
        self._edges_by_version[key.target].add(key)
        return key

    def get_migration(
        self,
        key: Transitional[VersionValue_co, VSource_co, VTarget_co],
    ) -> Migratable:
        """Return the migration for *key*."""
        if key.kind not in self._migrations:
            raise MigrationNotFoundError(self._name, key.edge)

        idx = bisect.bisect_left(self._migrations[key.kind], key)

        if (
            idx >= len(self._migrations[key.kind])
            or self._migrations[key.kind][idx] != key
        ):
            raise MigrationNotFoundError(self._name, key.edge)

        return self._migrations[key.kind][idx]

    def remove_migration(
        self: Self,
        key: Transitional[VersionValue_co, VSource_co, VTarget_co],
    ) -> None:
        """Remove a single migration.

        A migration with registered hooks cannot be removed —
        clear the hooks first.
        """
        if key in self._hooks:
            raise RegistryError(
                self._name,
                f"Cannot remove migration {key}: "
                "it has registered hooks. Clear hooks first.",
            )

        idx = bisect.bisect_left(self._migrations[key.kind], key)
        if (
            idx < len(self._migrations[key.kind])
            and self._migrations[key.kind][idx] == key
        ):
            del self._migrations[key.kind][idx]
            if not self._migrations[key.kind]:
                del self._migrations[key.kind]
            for endpoint in (key.source, key.target):
                bucket = self._edges_by_version.get(endpoint)
                if bucket is None:
                    continue
                bucket.discard(key)
                if not bucket:
                    del self._edges_by_version[endpoint]

    def clear_migrations(self: Self) -> None:
        """Remove all migrations from the registry."""
        self.clear_hooks()
        self._migrations.clear()
        self._edges_by_version.clear()

    def add_hook(
        self: Self,
        key: Transitional[VersionValue_co, VSource_co, VTarget_co],
        hook: Attachable,
    ) -> None:
        """Register a hook for a migration step."""
        self._hooks[key].append(hook)

    def get_hooks(
        self: Self,
        key: Transitional[VersionValue_co, VSource_co, VTarget_co],
    ) -> list[Attachable]:
        """Return hooks registered for a migration step.

        Returns an empty list when no hooks are present so graph
        construction and execution do not need to distinguish "no hooks"
        from a missing edge.
        """
        return list(self._hooks.get(key, []))

    def remove_hook(
        self: Self,
        key: Transitional[VersionValue_co, VSource_co, VTarget_co],
        hook: Attachable | None = None,
    ) -> None:
        """Remove hooks for a migration step."""
        if key not in self._hooks:
            raise RegistryError(self._name, f"No hooks registered for migration {key}")

        if hook is None:
            del self._hooks[key]
        elif hook in self._hooks[key]:
            self._hooks[key].remove(hook)
            if not self._hooks[key]:
                del self._hooks[key]
        else:
            raise ValueError(f"Hook {hook!r} is not registered for migration {key}")

    def clear_hooks(
        self: Self,
        key: Transitional[VersionValue_co, VSource_co, VTarget_co] | None = None,
    ) -> None:
        """Clear hooks from the registry."""
        if key is None:
            [hooks.clear() for hooks in self._hooks.values()]
            self._hooks.clear()

        if key is not None and key not in self._hooks:
            raise RegistryError(self._name, f"No hooks registered for migration {key}")

        if key is None:
            [hooks.clear() for hooks in self._hooks.values()]
            self._hooks.clear()
        else:
            self._hooks[key].clear()
            del self._hooks[key]
