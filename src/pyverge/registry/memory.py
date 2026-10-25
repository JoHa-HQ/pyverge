import bisect
from collections import defaultdict
from itertools import chain
from typing import Generic, Self, cast

from pyverge.core.types import (
    Attachable,
    MigrationFunc,
    ModelHandle,
    ModelKind,
    ModelVersionKey,
    VersionValue,
)
from pyverge.registry.errors import (
    CatalogError,
    GraphLockedError,
    MigrationConflictError,
    MigrationNotFoundError,
    MigrationPathError,
    ModelAlreadyRegisteredError,
    ModelConflictError,
    ModelNotFoundError,
)
from pyverge.versioning import (
    Comparable,
    ContentHasher,
    EdgeKey,
    Migratable,
    Transitional,
    VersionKey,
    VersionNode,
)


class InMemoryCatalog(Generic[VersionValue]):
    """In-memory registry for versioned models, migrations, and hooks.

    Provider-neutral: models are stored against an opaque :data:`ModelHandle`
    and lookups are keyed by version.  Class identification is a provider
    concern; the registry never imports an adapter.

    >>> from typing import Literal
    >>> import semver
    >>> from pydantic import BaseModel
    >>> from pyverge.registry import Registry
    >>> from pyverge.providers import PydanticModelAdapter
    >>> from pyverge.versioning import default_content_hasher
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
    >>> registry = Registry[semver.Version](hasher=default_content_hasher())
    >>> v1 = adapter.versionable(UserV1)
    >>> v2 = adapter.versionable(UserV2)
    >>> _ = registry.store_model(v1)
    >>> _ = registry.store_model(v2)
    >>> registry.get_model(v1).model is UserV1
    True
    >>> registry.latest("User").model is UserV2
    True
    """

    def __init__(
        self: Self,
        *,
        name: str | None = None,
        hasher: ContentHasher,
        index_content_hashes: bool = False,
    ) -> None:
        self._name = name or "registry"
        self._hasher = hasher
        self._locked = False
        self._index_content_hashes = index_content_hashes
        self._content_hash_index: dict[str, EdgeKey[VersionValue]] | None = (
            {} if index_content_hashes else None
        )
        self._by_versions: list[VersionNode[VersionValue]] = []
        self._by_kinds: dict[ModelKind, list[VersionNode[VersionValue]]] = defaultdict(
            list
        )
        self._by_models: dict[ModelHandle, VersionNode[VersionValue]] = {}
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
        try:
            if isinstance(index, Comparable):
                return self.has_model(index)
            if isinstance(index, Transitional):
                return self.has_migration(index)
        except (ModelNotFoundError, MigrationNotFoundError, TypeError):
            return False
        raise CatalogError(self._name, f"Unsupported index type: {type(index)}")

    def __getitem__(
        self, index: object
    ) -> VersionNode[VersionValue] | Migratable[VersionValue]:
        if isinstance(index, Comparable):
            return self.get_model(index)
        if isinstance(index, Transitional):
            return self.get_migration(index)
        raise CatalogError(self._name, f"Unsupported index type: {type(index)}")

    @property
    def versions(self: Self) -> list[VersionNode[VersionValue]]:
        return self._by_versions

    @property
    def name(self: Self) -> str:
        return self._name

    @property
    def kinds(self: Self) -> list[ModelKind]:
        return list(self._migrations.keys())

    @property
    def entities(self: Self) -> list[ModelKind]:
        return sorted(kind for kind, versions in self._by_kinds.items() if versions)

    @property
    def latest_version(self) -> VersionNode[VersionValue]:
        if not self._by_versions:
            raise CatalogError(self._name, "No versions registered")
        return self._by_versions[-1]

    def is_adjacent(self, key: Transitional[VersionValue]) -> bool:
        kind_versions = self._by_kinds[key.kind]
        from_idx = bisect.bisect_left(kind_versions, key.source)
        to_idx = bisect.bisect_left(kind_versions, key.target)
        return abs(from_idx - to_idx) == 1

    def models(self: Self, kind: ModelKind | None) -> frozenset[ModelHandle]:
        if kind is None:
            return frozenset(v.model for v in self._by_models.values())
        return frozenset(v.model for v in self._by_kinds.get(kind, []))

    def migrations(self: Self, kind: ModelKind) -> list[Migratable[VersionValue]]:
        return self._migrations.get(kind, [])

    def migrations_of(
        self: Self, key: Comparable[VersionValue]
    ) -> frozenset[Migratable[VersionValue]]:
        return frozenset(self._edges_by_version.get(key, ()))

    def kind_versions(self: Self, kind: ModelKind) -> list[VersionNode[VersionValue]]:
        return list(self._by_kinds.get(kind, []))

    def has_model(self: Self, key: Comparable) -> bool:
        idx = bisect.bisect_left(self._by_versions, key)
        return idx < len(self._by_versions) and self._by_versions[idx] == key

    def missing_references(
        self: Self,
        node: Comparable[VersionValue],
        *,
        require_registered: bool = True,
    ) -> frozenset[ModelVersionKey]:
        registered = cast(
            "VersionNode[VersionValue]",
            self.get_model(node)
            if require_registered
            else self.find_model(node) or node,
        )
        missing = []
        for kind, version in registered.references:
            key = VersionKey[VersionValue](_value=version, _kind=kind)
            if not self.has_model(key):
                missing.append((kind, version))
        return frozenset(missing)

    def _find_edge(
        self: Self,
        kind: ModelKind,
        pair: tuple[Comparable[VersionValue], Comparable[VersionValue]],
    ) -> Migratable[VersionValue]:
        edges = self._migrations.get(kind, [])
        key = EdgeKey.from_pair(*pair)
        idx = bisect.bisect_left(edges, key)
        if idx < len(edges) and edges[idx].edge == pair:
            return edges[idx]
        raise MigrationNotFoundError(self._name, pair)

    def has_migration(self: Self, key: Transitional[VersionValue]) -> bool:
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
        return self._find_edge(key.kind, key.edge)

    def has_hooks(self: Self, key: Transitional[VersionValue]) -> bool:
        return key in self._hooks

    def latest(self: Self, kind: ModelKind) -> VersionNode[VersionValue]:
        if kind not in self._by_kinds:
            raise CatalogError(self._name, "No versions registered")
        return self._by_kinds[kind][-1]

    def earliest(self: Self, kind: ModelKind) -> VersionNode[VersionValue]:
        if kind not in self._by_kinds:
            raise CatalogError(self._name, "No versions registered")
        return self._by_kinds[kind][0]

    def hooks(self: Self, key: Transitional | None = None) -> list[Attachable]:
        if key is None:
            return list(chain(*self._hooks.values()))
        return self._hooks[key]

    def copy(self: Self, name: str | None = None) -> "InMemoryCatalog[VersionValue]":
        new = cast(
            "InMemoryCatalog[VersionValue]",
            InMemoryCatalog(
                name=name or self._name,
                hasher=self._hasher,
                index_content_hashes=self._index_content_hashes,
            ),
        )
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
        if self._content_hash_index is not None:
            new._content_hash_index = dict(self._content_hash_index)
        return new

    def _ensure_mutable(self: Self, operation: str) -> None:
        if self._locked:
            raise GraphLockedError(self._name, operation)

    def lock(self: Self) -> "InMemoryCatalog[VersionValue]":
        self._locked = True
        snapshot = self.copy()
        snapshot._locked = True
        return snapshot

    def snapshot(self: Self) -> "InMemoryCatalog[VersionValue]":
        snapshot = self.copy()
        snapshot._locked = True
        return snapshot

    def find_edge_by_content_hash(self, value: str) -> EdgeKey[VersionValue] | None:
        if self._content_hash_index is None:
            return None
        return self._content_hash_index.get(value)

    def store_model(
        self: Self,
        version: VersionNode[VersionValue],
    ) -> VersionNode[VersionValue]:
        self._ensure_mutable("store_model")
        if version in self._by_versions:
            raise ModelAlreadyRegisteredError(
                catalog_name=self._name,
                version=version.version,
            )
        self._by_models[version.model] = version
        bisect.insort_left(self._by_versions, version)
        bisect.insort_left(self._by_kinds[version.version[0]], version)
        return version

    def reconcile_model(
        self: Self,
        version: VersionNode[VersionValue],
    ) -> VersionNode[VersionValue]:
        self._ensure_mutable("reconcile_model")
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
    ) -> VersionNode[VersionValue]:
        idx = bisect.bisect_left(self._by_versions, key)
        if idx < len(self._by_versions) and (model := self._by_versions[idx]) == key:
            return model
        raise ModelNotFoundError(self._name, key.version)

    def find_model(self: Self, key: Comparable) -> VersionNode[VersionValue] | None:
        idx = bisect.bisect_left(self._by_versions, key)
        if idx < len(self._by_versions) and (model := self._by_versions[idx]) == key:
            return model
        return None

    def get_model_by_handle(
        self: Self, handle: ModelHandle
    ) -> VersionNode[VersionValue]:
        if target := self._by_models.get(handle):
            return target
        raise ModelNotFoundError(self._name, handle)

    def remove_model(self: Self, key: Comparable) -> None:
        self._ensure_mutable("remove_model")

        version_idx = bisect.bisect_left(self._by_versions, key)
        kind_idx = bisect.bisect_left(self._by_kinds[key.kind], key)
        if (
            version_idx == len(self._by_versions)
            or self._by_versions[version_idx] != key
        ):
            raise CatalogError(self._name, f"Version {key} is not registered")

        affected = self.migrations_of(key)
        if affected:
            pairs = ", ".join(f"{e.source}→{e.target}" for e in sorted(affected))
            raise CatalogError(
                self._name,
                f"Cannot remove version {key}: it is referenced by migrations: {pairs}",
            )

        version = self._by_versions[version_idx]

        del self._by_kinds[key.kind][kind_idx]
        del self._by_models[version.model]
        del self._by_versions[version_idx]

    def remove_model_by_handle(self: Self, handle: ModelHandle) -> None:
        self._ensure_mutable("remove_model_by_handle")
        if handle not in self._by_models:
            raise ModelNotFoundError(self._name, handle)
        self.remove_model(self._by_models[handle])

    def clear_models(self: Self) -> None:
        self._ensure_mutable("clear_models")
        if self._migrations:
            raise CatalogError(self._name, "Clear migrations first")
        self._by_versions.clear()
        self._by_models.clear()
        self._by_kinds.clear()

    def delete_kind(self: Self, kind: ModelKind) -> None:  # noqa: C901
        self._ensure_mutable("delete_kind")
        versions = self.kind_versions(kind)
        if not versions:
            return
        version_set = set(versions)
        for version in versions:
            for edge in self.migrations_of(version):
                if edge.source not in version_set or edge.target not in version_set:
                    raise CatalogError(
                        self._name,
                        f"Cannot delete kind '{kind}': version is referenced "
                        f"by cross-kind migration {edge.source}→{edge.target}",
                    )
        for version in versions:
            for edge in list(self.migrations_of(version)):
                if edge.source in version_set and edge.target in version_set:
                    if self.has_hooks(edge):
                        self.clear_hooks(edge)
                    self.remove_migration(EdgeKey.from_version_edge(edge))
        for version in reversed(versions):
            try:
                self.remove_model(version)
            except CatalogError:
                pass

    def store_migration(
        self: Self,
        key: Migratable[VersionValue],
    ) -> MigrationFunc:
        self._ensure_mutable("store_migration")
        if any(v not in self._by_versions for v in key.edge):
            raise MigrationNotFoundError(self._name, key.edge)

        paths = self._migrations.get(key.kind, [])

        idx = bisect.bisect_left(paths, key)
        if idx < len(paths) and paths[idx] == key:
            existing = paths[idx]
            registered_hash = existing.content_hash(self._hasher)
            incoming_hash = key.content_hash(self._hasher)
            if registered_hash == incoming_hash:
                return existing.func
            raise MigrationConflictError(
                self._name,
                key.edge,
                registered_hash=registered_hash,
                incoming_hash=incoming_hash,
            )

        bisect.insort(self._migrations[key.kind], key)
        self._edges_by_version[key.source].add(key)
        self._edges_by_version[key.target].add(key)
        if self._content_hash_index is not None:
            edge_key = EdgeKey.from_version_edge(key)
            self._content_hash_index[key.content_hash(self._hasher)] = edge_key
        return key.func

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
        self._ensure_mutable("remove_migration")
        if key in self._hooks:
            raise CatalogError(
                self._name,
                f"Cannot remove migration {key}: "
                "it has registered hooks. Clear hooks first.",
            )

        idx = bisect.bisect_left(self._migrations[key.kind], key)
        if (
            idx < len(self._migrations[key.kind])
            and self._migrations[key.kind][idx] == key
        ):
            existing = self._migrations[key.kind][idx]
            del self._migrations[key.kind][idx]
            if not self._migrations[key.kind]:
                del self._migrations[key.kind]
            if self._content_hash_index is not None:
                self._content_hash_index.pop(existing.content_hash(self._hasher), None)
            for endpoint in (key.source, key.target):
                bucket = self._edges_by_version.get(endpoint)
                if bucket is None:
                    continue
                bucket.discard(key)
                if not bucket:
                    del self._edges_by_version[endpoint]

    def clear_migrations(self: Self) -> None:
        self._ensure_mutable("clear_migrations")
        self.clear_hooks()
        self._migrations.clear()
        self._edges_by_version.clear()
        if self._content_hash_index is not None:
            self._content_hash_index.clear()

    def migration_path(
        self: Self,
        from_version: Comparable[VersionValue],
        to_version: Comparable[VersionValue],
    ) -> list[tuple[VersionNode[VersionValue], VersionNode[VersionValue]]]:
        if from_version.kind != to_version.kind:
            raise CatalogError(
                self._name,
                f"Cannot find path across kinds: "
                f"{from_version.kind} != {to_version.kind}",
            )

        kind_versions = self.kind_versions(from_version.kind)

        if from_version not in kind_versions:
            raise MigrationPathError(
                self._name,
                from_version,
                to_version,
                f"Version {from_version} is not registered",
            )
        if to_version not in kind_versions:
            raise MigrationPathError(
                self._name,
                (from_version, to_version),
            )

        lo = bisect.bisect_left(kind_versions, from_version)
        hi = bisect.bisect_left(kind_versions, to_version)
        if lo == hi:
            return []

        step = 1 if lo < hi else -1
        path: list[tuple[VersionNode[VersionValue], VersionNode[VersionValue]]] = []
        current = kind_versions[lo]
        while lo != hi:
            nxt = kind_versions[lo + step]
            edge_key = EdgeKey.from_pair(current, nxt)
            if self.has_migration(edge_key):
                path.append((current, nxt))
                current = nxt
                lo += step
            else:
                raise MigrationPathError(
                    self._name,
                    current,
                    nxt,
                    f"No migration key is found ({current}, {nxt})",
                )
        return path

    def remove_migration_range(
        self: Self,
        from_version: Comparable[VersionValue],
        to_version: Comparable[VersionValue],
    ) -> None:
        self._ensure_mutable("remove_migration_range")
        if from_version.version[0] != to_version.version[0]:
            raise CatalogError(
                self._name,
                f"Cannot remove range across kinds: "
                f"{from_version.version[0]} != {to_version.version[0]}",
            )

        kind_versions = self.kind_versions(from_version.version[0])
        lo = bisect.bisect_left(kind_versions, from_version)
        hi = bisect.bisect_left(kind_versions, to_version)

        keys_to_remove: list[EdgeKey[VersionValue]] = []
        for i in range(lo, hi):
            edge_key = EdgeKey.from_pair(kind_versions[i], kind_versions[i + 1])
            if not self.has_migration(edge_key):
                continue
            if self.is_adjacent(edge_key):
                msg = (
                    f"Cannot remove critical migration {edge_key.source}→"
                    f"{edge_key.target} in range. Remove it individually with "
                    "force=True or remove hooks first."
                )
                raise CatalogError(self._name, msg)
            if self.has_hooks(edge_key):
                raise CatalogError(
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
        self._ensure_mutable("add_hook")
        self._hooks[key].append(hook)

    def get_hooks(
        self: Self,
        key: Transitional[VersionValue],
    ) -> list[Attachable]:
        return list(self._hooks.get(key, []))

    def remove_hook(
        self: Self,
        key: Transitional[VersionValue],
        hook: Attachable | None = None,
    ) -> None:
        self._ensure_mutable("remove_hook")
        if key not in self._hooks:
            raise CatalogError(self._name, f"No hooks registered for migration {key}")

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
        self._ensure_mutable("clear_hooks")
        if key is None:
            [hooks.clear() for hooks in self._hooks.values()]
            self._hooks.clear()

        if key is not None and key not in self._hooks:
            raise CatalogError(self._name, f"No hooks registered for migration {key}")

        if key is None:
            [hooks.clear() for hooks in self._hooks.values()]
            self._hooks.clear()
        else:
            self._hooks[key].clear()
            del self._hooks[key]


#: Backward-compatible name for the in-memory catalog.
Registry = InMemoryCatalog
