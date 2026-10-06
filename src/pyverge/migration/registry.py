import bisect
from collections import defaultdict
from itertools import chain
from typing import Generic, Self, cast

from pyverge.core.exceptions import (
    MigrationAlreadyRegisteredError,
    MigrationError,
    MigrationNotFoundError,
    ModelAlreadyRegisteredError,
    ModelConflictError,
    ModelNotFoundError,
    RegistryError,
)
from pyverge.core.types import (
    Attachable,
    Comparable,
    ManagerKey,
    Migratable,
    MigrationFunc,
    ModelHandle,
    ModelKind,
    ModelVersionKey,
    Transitional,
    Versionable,
    VersionValue,
)
from pyverge.core.versioning import (
    SentinelEdge,
    VersionNode,
)


class Registry(Generic[VersionValue]):
    """Ordered storage for versioned models, migrations, and hooks.

    Provider-neutral: models are stored against an opaque :data:`ModelHandle`
    and lookups are keyed by version.  Class identification is the engine's
    concern, through the adapter.

    >>> from typing import Literal
    >>> import semver
    >>> from pydantic import BaseModel
    >>> from pyverge.migration import PydanticModelAdapter, Registry
    >>> adapter = PydanticModelAdapter()
    >>> class UserV1(BaseModel):
    ...     kind: Literal["User"] = "User"
    ...     version: Literal["1.0.0"] = "1.0.0"
    ...     name: str
    >>> class UserV2(BaseModel):
    ...     kind: Literal["User"] = "User"
    ...     version: Literal["2.0.0"] = "2.0.0"
    ...     name: str
    ...     age: int | None = None
    >>> registry = Registry[semver.Version]()
    >>> v1 = adapter.versionable(UserV1)
    >>> v2 = adapter.versionable(UserV2)
    >>> _ = registry.store_model(v1)
    >>> _ = registry.store_model(v2)
    >>> registry.get_model(v1).model is UserV1
    True
    >>> registry.latest("User").model is UserV2
    True
    """

    def __init__(self: Self, *, name: str | None = None) -> None:
        self._name = name or "registry"
        self._by_versions: list[Versionable[VersionValue]] = []
        self._by_kinds: dict[ModelKind, list[Versionable[VersionValue]]] = defaultdict(
            list
        )
        self._by_models: dict[ModelHandle, Versionable[VersionValue]] = {}
        self._migrations: dict[ModelKind, list[Migratable[VersionValue]]] = defaultdict(
            list
        )
        self._edges_by_version: dict[
            Comparable[VersionValue], set[Migratable[VersionValue]]
        ] = defaultdict(set)
        self._hooks: dict[Transitional[VersionValue], list[Attachable]] = defaultdict(
            list
        )

    def __contains__(self, index: object) -> bool:
        """Membership of a version node or migration edge.

        Typed only: raw tuples are fluent sugar owned by the manager.
        """
        try:
            if isinstance(index, Versionable):
                return self.has_model(index)
            if isinstance(index, Transitional):
                return self.has_migration(index)
        except (ModelNotFoundError, MigrationNotFoundError, TypeError):
            return False
        raise RegistryError(self._name, f"Unsupported index type: {type(index)}")

    def __getitem__(
        self, index: object
    ) -> Versionable[VersionValue] | Migratable[VersionValue]:
        """Lookup by version node or migration edge (typed only)."""
        if isinstance(index, Versionable):
            return self.get_model(index)
        if isinstance(index, Transitional):
            return self.get_migration(index)
        raise RegistryError(self._name, f"Unsupported index type: {type(index)}")

    @property
    def versions(self: Self) -> list[Versionable[VersionValue]]:
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
    def latest_version(self) -> Versionable[VersionValue]:
        """The most recently registered version overall."""
        if not self._by_versions:
            raise RegistryError(self._name, "No versions registered")
        return self._by_versions[-1]

    def is_adjacent(self, key: Transitional[VersionValue]) -> bool:
        """True if *key* connects two neighbours in the kind's version list."""
        kind_versions = self._by_kinds[key.kind]
        from_idx = bisect.bisect_left(kind_versions, key.source)
        to_idx = bisect.bisect_left(kind_versions, key.target)
        return abs(from_idx - to_idx) == 1

    def models(self: Self, kind: ModelKind | None) -> frozenset[ModelHandle]:
        if kind is None:
            return frozenset(
                v.model for v in self._by_models.values() if v.model is not None
            )
        return frozenset(
            v.model for v in self._by_kinds.get(kind, []) if v.model is not None
        )

    def migrations(self: Self, kind: ModelKind) -> list[Migratable[VersionValue]]:
        """Registered migrations for *kind*."""
        return self._migrations.get(kind, [])

    def migrations_of(
        self: Self, key: Comparable[VersionValue]
    ) -> frozenset[Migratable[VersionValue]]:
        """Migration edges referencing *key* as source or target."""
        return frozenset(self._edges_by_version.get(key, ()))

    def kind_versions(self: Self, kind: ModelKind) -> list[Versionable[VersionValue]]:
        return list(self._by_kinds.get(kind, []))

    def has_model(self: Self, key: Comparable) -> bool:
        idx = bisect.bisect_left(self._by_versions, key)
        return idx < len(self._by_versions) and self._by_versions[idx] == key

    def missing_references(
        self: Self, node: Versionable[VersionValue]
    ) -> frozenset[ModelVersionKey]:
        """The ``(kind, version)`` pairs *node* declares but that are absent.

        *node* must itself be registered.
        """
        registered = self.get_model(node)
        missing = []
        for kind, version in registered.references:
            sentinel = VersionNode[VersionValue](
                _model=None, _value=version, _kind=kind
            )
            if not self.has_model(sentinel):
                missing.append((kind, version))
        return frozenset(missing)

    def _find_edge(
        self: Self,
        kind: ModelKind,
        pair: tuple[Comparable[VersionValue], Comparable[VersionValue]],
    ) -> Migratable[VersionValue]:
        edges = self._migrations.get(kind, [])
        sentinel = SentinelEdge.from_pair(*pair)
        idx = bisect.bisect_left(edges, sentinel)
        if idx < len(edges) and edges[idx].edge == pair:
            return edges[idx]
        raise MigrationNotFoundError(self._name, pair)

    def has_migration(self: Self, key: Transitional[VersionValue]) -> bool:
        """Whether a migration edge is registered.

        Accepts any transitional edge (``VersionEdge``/``SentinelEdge`` or any
        object exposing ``kind`` and ``edge``).
        """
        try:
            self._find_edge(key.kind, key.edge)
            return True
        except MigrationNotFoundError:
            return False

    def is_critical_edge(self: Self, key: Transitional[VersionValue]) -> bool:
        idx = bisect.bisect_left(self._migrations[key.kind], key)
        return len(self._migrations[key.kind]) > 2 and (  # noqa: PLR2004
            idx > 0 or idx < len(self._migrations[key.kind]) - 1
        )

    def get_migration_by_edge(
        self: Self,
        key: Transitional[VersionValue],
    ) -> Migratable[VersionValue]:
        """Return the registered migration edge for any transitional *key*."""
        return self._find_edge(key.kind, key.edge)

    def has_hooks(self: Self, key: Transitional[VersionValue]) -> bool:
        return key in self._hooks

    def latest(self: Self, kind: ModelKind) -> Versionable[VersionValue]:
        if kind not in self._by_kinds:
            raise RegistryError(self._name, "No versions registered")
        return self._by_kinds[kind][-1]

    def earliest(self: Self, kind: ModelKind) -> Versionable[VersionValue]:
        if kind not in self._by_kinds:
            raise RegistryError(self._name, "No versions registered")
        return self._by_kinds[kind][0]

    def hooks(self: Self, key: Transitional | None) -> list[Attachable]:
        if key is None:
            return list(chain(*self._hooks.values()))
        return self._hooks[key]

    def copy(self: Self, name: str | None = None) -> "Registry[VersionValue]":
        new = cast("Registry[VersionValue]", Registry(name=name))
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
        version: Versionable[VersionValue],
    ) -> Versionable[VersionValue]:
        """Register a model at *version*.

        Strict: a duplicate ``(kind, version)`` raises
        :class:`ModelAlreadyRegisteredError`.  Callers that re-register
        identical shapes should use :meth:`reconcile_model` instead.
        """
        if version in self._by_versions:
            raise ModelAlreadyRegisteredError(
                registry_name=self._name,
                version=version.version,
            )
        if version.model is not None:
            self._by_models[version.model] = version
        bisect.insort_left(self._by_versions, version)
        bisect.insort_left(self._by_kinds[version.version[0]], version)
        return version

    def reconcile_model(
        self: Self,
        version: Versionable[VersionValue],
    ) -> Versionable[VersionValue]:
        """Register *version*, reconciling against an existing registration.

        The fallback store: an unregistered version is stored; an identical
        re-registration (same ``fields`` surface) is a no-op returning the
        existing node; a differing surface raises :class:`ModelConflictError`.
        Reconciliation belongs to storage, not the engine.
        """
        try:
            existing = self.get_model(version)
        except ModelNotFoundError:
            return self.store_model(version)
        if existing.fields != version.fields:
            raise ModelConflictError(
                self._name,
                version.version,
                existing.fields,
                version.fields,
            )
        return existing

    def get_model(
        self: Self,
        key: Comparable,
    ) -> Versionable[VersionValue]:
        idx = bisect.bisect_left(self._by_versions, key)
        if idx < len(self._by_versions) and (model := self._by_versions[idx]) == key:
            return model
        raise ModelNotFoundError(self._name, key.version)

    def get_model_by_handle(
        self: Self, handle: ModelHandle
    ) -> Versionable[VersionValue]:
        """Return the registered versionable for the opaque *handle*."""
        if target := self._by_models.get(handle):
            return target
        raise ModelNotFoundError(self._name, handle)

    def remove_model(self: Self, key: Comparable) -> None:
        """Refuse to remove a version still referenced by a migration edge."""

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
        if version.model is not None:
            del self._by_models[version.model]
        del self._by_versions[version_idx]

    def remove_model_by_handle(self: Self, handle: ModelHandle) -> None:
        """Remove the registered versionable for the opaque *handle*."""
        if handle not in self._by_models:
            raise ModelNotFoundError(self._name, handle)
        self.remove_model(self._by_models[handle])

    def clear_models(self: Self) -> None:
        if self._migrations:
            raise RegistryError(self._name, "Clear migrations first")
        self._by_versions.clear()
        self._by_models.clear()
        self._by_kinds.clear()

    def store_migration(
        self: Self,
        key: Migratable[VersionValue],
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
        key: Transitional[VersionValue],
    ) -> Migratable[VersionValue]:
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
        key: Transitional[VersionValue],
    ) -> None:
        """Remove a migration; refuses one with registered hooks."""
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

    def migration_path(
        self: Self,
        from_version: Versionable[VersionValue],
        to_version: Versionable[VersionValue],
    ) -> list[tuple[Versionable[VersionValue], Versionable[VersionValue]]]:
        """Return a complete migration chain between two versions.

        Both endpoints must be registered versions of the same kind and a
        registered migration must exist on every adjacent step.
        """
        if from_version.kind != to_version.kind:
            raise RegistryError(
                self._name,
                f"Cannot find path across kinds: "
                f"{from_version.kind} != {to_version.kind}",
            )

        kind_versions = self.kind_versions(from_version.kind)

        if from_version not in kind_versions:
            raise MigrationError(
                self._name,
                from_version,
                to_version,
                f"Version {from_version} is not registered",
            )
        if to_version not in kind_versions:
            raise MigrationError(
                self._name,
                (from_version, to_version),
            )

        lo = kind_versions.index(from_version)
        hi = kind_versions.index(to_version)
        if lo == hi:
            return []

        step = 1 if lo < hi else -1
        path: list[tuple[Versionable[VersionValue], Versionable[VersionValue]]] = []
        current = from_version
        while lo != hi:
            nxt = kind_versions[lo + step]
            edge_key = SentinelEdge.from_pair(current, nxt)
            if self.has_migration(edge_key):
                path.append((current, nxt))
                current = nxt
                lo += step
            else:
                raise MigrationError(
                    self._name,
                    current,
                    nxt,
                    f"No migration key is found ({current}, {nxt})",
                )
        return path

    def remove_migration_range(
        self: Self,
        from_version: Versionable[VersionValue],
        to_version: Versionable[VersionValue],
    ) -> None:
        """Remove every migration on edges between two versions of one kind.

        Refuses to remove a critical (adjacent) edge, or one carrying hooks.
        """
        if from_version.version[0] != to_version.version[0]:
            raise RegistryError(
                self._name,
                f"Cannot remove range across kinds: "
                f"{from_version.version[0]} != {to_version.version[0]}",
            )

        kind_versions = self.kind_versions(from_version.version[0])
        lo = bisect.bisect_left(kind_versions, from_version)
        hi = bisect.bisect_left(kind_versions, to_version)

        keys_to_remove: list[SentinelEdge[VersionValue]] = []
        for i in range(lo, hi):
            edge_key = SentinelEdge.from_pair(kind_versions[i], kind_versions[i + 1])
            if not self.has_migration(edge_key):
                continue
            if self.is_adjacent(edge_key):
                msg = (
                    f"Cannot remove critical migration {edge_key.source}→"
                    f"{edge_key.target} in range. Remove it individually with "
                    "force=True or remove hooks first."
                )
                raise RegistryError(self._name, msg)
            if self.has_hooks(edge_key):
                raise RegistryError(
                    self._name,
                    f"Cannot remove migration {edge_key.source}→{edge_key.target}. "
                    "Remove hooks first.",
                )
            keys_to_remove.append(edge_key)

        for edge_key in keys_to_remove:
            self.remove_migration(edge_key)

    def add_hook(
        self: Self,
        key: Transitional[VersionValue],
        hook: Attachable,
    ) -> None:
        """Register a hook for a migration step."""
        self._hooks[key].append(hook)

    def get_hooks(
        self: Self,
        key: Transitional[VersionValue],
    ) -> list[Attachable]:
        """
        Returns an empty list when no hooks are present so graph
        construction and execution do not need to distinguish "no hooks"
        from a missing edge.
        """
        return list(self._hooks.get(key, []))

    def remove_hook(
        self: Self,
        key: Transitional[VersionValue],
        hook: Attachable | None = None,
    ) -> None:
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
        key: Transitional[VersionValue] | None = None,
    ) -> None:
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


_ = ManagerKey
