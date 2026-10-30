import bisect
from collections import defaultdict
from collections.abc import Mapping
from itertools import chain
from types import MappingProxyType
from typing import Generic, Self, cast

from pyverge.core.types import (
    Attachable,
    MigrationFunc,
    ModelKind,
    VersionValue,
)
from pyverge.registry.errors import (
    CatalogError,
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
    EdgeEntry,
    EdgeKey,
    Migratable,
    ModelRef,
    NodeEntry,
    NodeId,
    Transitional,
    VersionEdge,
    VersionNode,
)
from pyverge.versioning.errors import NodeConflictError


class InMemoryCatalog(Generic[VersionValue]):
    """In-memory registry for versioned models, migrations, and hooks.

    Provider-neutral: models are stored against an opaque :data:`ModelHandle`
    and lookups are keyed by version.  Class identification is a provider
    concern; the registry never imports an adapter.

    >>> from typing import Literal
    >>> import semver
    >>> from pydantic import BaseModel
    >>> from pyverge.registry import Registry
    >>> from pyverge.schemas import ModelCodec
    >>> from pyverge.schemas import PydanticModelAdapter
    >>> from pyverge.versioning import default_content_hasher
    >>> adapter = PydanticModelAdapter(codec=ModelCodec(
            namespace="",
            version_property="version",
            kind_property="kind",
        ))
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
    >>> _ = registry.store(v1, mode="strict")
    >>> _ = registry.store(v2, mode="strict")
    >>> registry.get_model(v1).model_id == "tests.UserV1"
    True
    >>> registry.latest("User").model_id == "tests.UserV2"
    True
    """

    def __init__(
        self: Self,
        *,
        name: str | None = None,
        namespace: str = "",
        hasher: ContentHasher,
        index_content_hashes: bool = False,
    ) -> None:
        self._name = name or "registry"
        self._namespace = namespace
        self._hasher = hasher
        self._index_content_hashes = index_content_hashes
        self._content_hash_index: dict[str, EdgeKey[VersionValue]] | None = (
            {} if index_content_hashes else None
        )
        self._by_versions: list[NodeEntry] = []
        self._by_kinds: dict[ModelKind, list[NodeEntry]] = defaultdict(list)
        self._by_models: dict[ModelRef, VersionNode[VersionValue]] = {}
        self._migrations: dict[ModelKind, list[EdgeEntry]] = defaultdict(list)
        self._edges_by_version: dict[Comparable[VersionValue], set[EdgeEntry]] = (
            defaultdict(set)
        )
        self._hooks: dict[Transitional[VersionValue], list[Attachable]] = defaultdict(
            list
        )

    def __contains__(self, index: object) -> bool:
        try:
            if isinstance(index, Comparable):
                return self.has_entry(index)
            if isinstance(index, Transitional):
                return self.has_edge(EdgeKey.from_pair(*index.key))
        except (ModelNotFoundError, MigrationNotFoundError, TypeError):
            return False
        raise CatalogError(self._name, f"Unsupported index type: {type(index)}")

    def __getitem__(self, index: object) -> NodeEntry | EdgeEntry:
        if isinstance(index, Comparable):
            return self.get_entry(index)
        if isinstance(index, Transitional):
            return self.get_edge(EdgeKey.from_pair(*index.key))
        raise CatalogError(self._name, f"Unsupported index type: {type(index)}")

    @property
    def versions(self: Self) -> list[VersionNode[VersionValue]]:
        return [
            cast("VersionNode[VersionValue]", entry)
            for entry in self._by_versions
            if entry.is_model
        ]

    @property
    def entries(self: Self) -> list[NodeEntry]:
        return self._by_versions

    @property
    def name(self: Self) -> str:
        return self._name

    @property
    def namespace(self: Self) -> str:
        return self._namespace

    @property
    def content_hashes(self: Self) -> Mapping[str, EdgeKey[VersionValue]]:
        return MappingProxyType(dict(self._content_hash_index or {}))

    @property
    def kinds(self: Self) -> list[ModelKind]:
        return list(self._migrations.keys())

    @property
    def entities(self: Self) -> list[ModelKind]:
        return sorted(kind for kind, versions in self._by_kinds.items() if versions)

    @property
    def latest_version(self) -> VersionNode[VersionValue]:
        versions = self.versions
        if not versions:
            raise CatalogError(self._name, "No versions registered")
        return versions[-1]

    def is_adjacent(self, key: Transitional[VersionValue]) -> bool:
        kind_versions = self._by_kinds[key.kind]
        from_idx = bisect.bisect_left(kind_versions, key.source)
        to_idx = bisect.bisect_left(kind_versions, key.target)
        return abs(from_idx - to_idx) == 1

    def models(self: Self, kind: ModelKind | None) -> frozenset[ModelRef]:
        if kind is None:
            return frozenset(self._by_models)
        return frozenset(
            cast("ModelRef", entry.modelref)
            for entry in self._by_kinds.get(kind, [])
            if entry.modelref is not None
        )

    def migrations(self: Self, kind: ModelKind) -> list[Migratable[VersionValue]]:
        return [
            cast("Migratable[VersionValue]", entry)
            for entry in self._migrations.get(kind, [])
            if entry.is_executable
        ]

    def edges(self: Self, kind: ModelKind) -> list[EdgeEntry]:
        return list(self._migrations.get(kind, []))

    def migrations_of(
        self: Self, key: Comparable[VersionValue]
    ) -> frozenset[Migratable[VersionValue]]:
        return frozenset(
            cast("Migratable[VersionValue]", edge)
            for edge in self._edges_by_version.get(key, ())
            if edge.is_executable
        )

    def edges_of(self: Self, key: Comparable[VersionValue]) -> frozenset[EdgeEntry]:
        return frozenset(self._edges_by_version.get(key, ()))

    def kind_versions(self: Self, kind: ModelKind) -> list[VersionNode[VersionValue]]:
        return [
            cast("VersionNode[VersionValue]", entry)
            for entry in self._by_kinds.get(kind, [])
            if entry.is_model
        ]

    def kind_entries(self: Self, kind: ModelKind) -> list[NodeEntry]:
        return list(self._by_kinds.get(kind, []))

    def has_model(self: Self, key: Comparable) -> bool:
        idx = bisect.bisect_left(self._by_versions, key)
        return idx < len(self._by_versions) and self._by_versions[idx] == key

    def missing_references(
        self: Self,
        node: Comparable[VersionValue],
        *,
        require_registered: bool = True,
    ) -> frozenset[NodeId]:
        registered = cast(
            "VersionNode[VersionValue]",
            self.get_model(node)
            if require_registered
            else self.find_model(node) or node,
        )
        missing = []
        for reference in registered.references:
            resolved = reference
            if not resolved.namespace and self._namespace:
                resolved = NodeId(
                    namespace=self._namespace,
                    kind=resolved.kind,
                    version=resolved.version,
                )
            if not self.has_model(resolved):
                missing.append(resolved)
        return frozenset(missing)

    def _find_edge(
        self: Self,
        kind: ModelKind,
        pair: tuple[NodeId[VersionValue], NodeId[VersionValue]],
    ) -> EdgeEntry:
        edges = self._migrations.get(kind, [])
        key = EdgeKey.from_pair(*pair)
        idx = bisect.bisect_left(edges, key)
        if idx < len(edges) and edges[idx].key == pair:
            return edges[idx]
        raise MigrationNotFoundError(self._name, pair)

    def has_migration(self: Self, key: Transitional[VersionValue]) -> bool:
        try:
            return self._find_edge(key.kind, key.key).is_executable
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
        edge = self._find_edge(key.kind, key.key)
        if not edge.is_executable:
            raise MigrationNotFoundError(self._name, key.key)
        return cast("Migratable[VersionValue]", edge)

    def has_hooks(self: Self, key: Transitional[VersionValue]) -> bool:
        return key in self._hooks

    def latest(self: Self, kind: ModelKind) -> VersionNode[VersionValue]:
        versions = self.kind_versions(kind)
        if not versions:
            raise CatalogError(self._name, "No versions registered")
        return versions[-1]

    def earliest(self: Self, kind: ModelKind) -> VersionNode[VersionValue]:
        versions = self.kind_versions(kind)
        if not versions:
            raise CatalogError(self._name, "No versions registered")
        return versions[0]

    def hooks(self: Self, key: Transitional | None = None) -> list[Attachable]:
        if key is None:
            return list(chain(*self._hooks.values()))
        return self._hooks[key]

    def copy(self: Self, name: str | None = None) -> "InMemoryCatalog[VersionValue]":
        new = cast(
            "InMemoryCatalog[VersionValue]",
            InMemoryCatalog(
                name=name or self._name,
                namespace=self._namespace,
                hasher=self._hasher,
                index_content_hashes=self._index_content_hashes,
            ),
        )
        new.copy_from(self)
        return new

    def copy_from(self: Self, source: "InMemoryCatalog[VersionValue]") -> None:
        """Replace this catalog's stores with a copy of ``source``."""
        self._by_versions = list(source._by_versions)
        self._by_kinds = defaultdict(
            list, {k: list(v) for k, v in source._by_kinds.items()}
        )
        self._by_models = dict(source._by_models)
        self._migrations = defaultdict(
            list, {k: list(v) for k, v in source._migrations.items()}
        )
        self._edges_by_version = defaultdict(
            set, {v: set(s) for v, s in source._edges_by_version.items()}
        )
        self._hooks = defaultdict(list, {k: list(v) for k, v in source._hooks.items()})
        if source._content_hash_index is not None:
            self._content_hash_index = dict(source._content_hash_index)

    def find_edge_by_content_hash(self, value: str) -> EdgeKey[VersionValue] | None:
        if self._content_hash_index is None:
            return None
        return self._content_hash_index.get(value)

    def store(self: Self, entry: NodeEntry) -> NodeEntry:
        """Insert a new node entry; reject duplicates."""
        if self.find_entry(entry) is not None:
            raise ModelAlreadyRegisteredError(
                catalog_name=self._name,
                version=entry,
            )
        bisect.insort_left(self._by_versions, entry)
        bisect.insort_left(self._by_kinds[entry.kind], entry)
        if entry.modelref is not None:
            self._by_models[cast("ModelRef", entry.modelref)] = cast(
                "VersionNode[VersionValue]", entry
            )
        return entry

    def hydrate(
        self: Self, entry: VersionNode[VersionValue]
    ) -> VersionNode[VersionValue]:
        """Upgrade a key-only entry with its full version node.

        Hydration is distinct from reconciliation: it installs the model
        payload for an identity that is already known (or is new).  A full node
        and a key-only entry cannot both exist for the same identity.
        """
        if not isinstance(entry, VersionNode):
            raise TypeError(f"Hydration requires a VersionNode, got {type(entry)!r}")
        existing = self.find_entry(entry)
        if existing is None:
            return cast("VersionNode[VersionValue]", self.store(entry))
        if isinstance(existing, VersionNode):
            return cast("VersionNode[VersionValue]", self.reconcile(entry))
        self.remove_entry(existing)
        return cast("VersionNode[VersionValue]", self.store(entry))

    def reconcile(self: Self, entry: NodeEntry) -> NodeEntry:
        """Insert or reconcile an existing node entry."""
        existing = self.find_entry(entry)
        if existing is None:
            return self.store(entry)
        if not existing.is_model and entry.is_model:
            raise CatalogError(
                self._name,
                f"Cannot reconcile key-only entry {entry}; hydrate it instead",
            )
        try:
            resolved = entry.reconcile(existing)
        except NodeConflictError as error:
            raise ModelConflictError(
                self._name,
                entry,
                existing.fields,
                entry.fields,
            ) from error
        if resolved is not existing:
            self.remove_entry(existing)
            return self.store(resolved)
        return existing

    def find_entry(self: Self, key: Comparable) -> NodeEntry | None:
        idx = bisect.bisect_left(self._by_versions, key)
        if idx < len(self._by_versions) and self._by_versions[idx] == key:
            return self._by_versions[idx]
        return None

    def get_entry(self: Self, key: Comparable) -> NodeEntry:
        if entry := self.find_entry(key):
            return entry
        raise ModelNotFoundError(self._name, key.version)

    def has_entry(self: Self, key: Comparable) -> bool:
        return self.find_entry(key) is not None

    def remove_entry(self: Self, entry: NodeEntry) -> None:
        """Remove a node entry and its conditional secondary indexes."""
        idx = bisect.bisect_left(self._by_versions, entry)
        if idx < len(self._by_versions) and self._by_versions[idx] == entry:
            del self._by_versions[idx]
        kind_entries = self._by_kinds[entry.kind]
        idx = bisect.bisect_left(kind_entries, entry)
        if idx < len(kind_entries) and kind_entries[idx] == entry:
            del kind_entries[idx]
        if entry.modelref is not None:
            self._by_models.pop(cast("ModelRef", entry.modelref), None)

    def store_edge(self: Self, entry: EdgeEntry) -> EdgeEntry:
        """Store a full executable edge or a key-only edge entry."""
        paths = self._migrations[entry.kind]
        idx = bisect.bisect_left(paths, entry)
        if idx < len(paths) and paths[idx] == entry:
            existing = paths[idx]
            if isinstance(entry, VersionEdge) and not isinstance(existing, VersionEdge):
                del paths[idx]
                for endpoint in (existing.source, existing.target):
                    bucket = self._edges_by_version.get(endpoint)
                    if bucket is not None:
                        bucket.discard(existing)
                        if not bucket:
                            del self._edges_by_version[endpoint]
            else:
                if isinstance(existing, VersionEdge) and isinstance(entry, VersionEdge):
                    registered_hash = existing.content_hash(self._hasher)
                    incoming_hash = entry.content_hash(self._hasher)
                    if registered_hash != incoming_hash:
                        raise MigrationConflictError(
                            self._name,
                            entry.key,
                            registered_hash=registered_hash,
                            incoming_hash=incoming_hash,
                        )
                return existing
        bisect.insort(paths, entry)
        self._edges_by_version[entry.source].add(entry)
        self._edges_by_version[entry.target].add(entry)
        if isinstance(entry, VersionEdge) and self._content_hash_index is not None:
            edge_key = EdgeKey.from_version_edge(entry)
            self._content_hash_index[entry.content_hash(self._hasher)] = edge_key
        return entry

    def has_edge(self: Self, key: EdgeKey[VersionValue]) -> bool:
        paths = self._migrations.get(key.kind, [])
        idx = bisect.bisect_left(paths, key)
        return idx < len(paths) and paths[idx] == key

    def get_edge(self: Self, key: EdgeKey[VersionValue]) -> EdgeEntry:
        paths = self._migrations.get(key.kind, [])
        idx = bisect.bisect_left(paths, key)
        if idx < len(paths) and paths[idx] == key:
            return paths[idx]
        raise MigrationNotFoundError(self._name, key.key)

    def get_model(
        self: Self,
        key: Comparable,
    ) -> VersionNode[VersionValue]:
        entry = self.find_entry(key)
        if isinstance(entry, VersionNode):
            return entry
        raise ModelNotFoundError(self._name, key.version)

    def find_model(self: Self, key: Comparable) -> VersionNode[VersionValue] | None:
        entry = self.find_entry(key)
        return entry if isinstance(entry, VersionNode) else None

    def get_model_by_ref(self: Self, ref: ModelRef) -> VersionNode[VersionValue]:
        if target := self._by_models.get(ref):
            return target
        raise ModelNotFoundError(self._name, ref)

    def remove_model(self: Self, key: Comparable) -> None:

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
        modelref = getattr(version, "modelref", None)
        if modelref is not None:
            self._by_models.pop(modelref, None)
        del self._by_versions[version_idx]

    def remove_model_by_ref(self: Self, ref: ModelRef) -> None:
        if ref not in self._by_models:
            raise ModelNotFoundError(self._name, ref)
        self.remove_model(self._by_models[ref])

    def clear_models(self: Self) -> None:
        if self._migrations:
            raise CatalogError(self._name, "Clear migrations first")
        self._by_versions.clear()
        self._by_models.clear()
        self._by_kinds.clear()

    def delete_kind(self: Self, kind: ModelKind) -> None:  # noqa: C901
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
        if not isinstance(key, VersionEdge):
            raise TypeError(
                f"Executable migration requires VersionEdge, got {type(key)}"
            )
        if any(v not in self._by_versions for v in key.key):
            raise MigrationNotFoundError(self._name, key.key)
        stored = self.store_edge(key)
        if not isinstance(stored, VersionEdge):
            raise TypeError("stored edge is not executable")
        return stored.func

    def get_migration(
        self,
        key: Transitional[VersionValue],
    ) -> Migratable[VersionValue]:
        return self.get_migration_by_edge(key)

    def remove_migration(
        self: Self,
        key: Transitional[VersionValue],
    ) -> None:
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
            if self._content_hash_index is not None and isinstance(
                existing, VersionEdge
            ):
                self._content_hash_index.pop(existing.content_hash(self._hasher), None)
            for endpoint in (key.source, key.target):
                bucket = self._edges_by_version.get(endpoint)
                if bucket is None:
                    continue
                bucket.discard(key)
                if not bucket:
                    del self._edges_by_version[endpoint]

    def clear_migrations(self: Self) -> None:
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
        kind_versions = self.kind_versions(from_version.kind)
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
