import bisect
from collections import defaultdict
from collections.abc import Mapping, Sequence
from itertools import chain
from types import MappingProxyType
from typing import Any, Generic, Self, cast

from pyverge.core.types import (
    Attachable,
    MigrationFunc,
    ModelKind,
    VersionValue,
)
from pyverge.migrations.identity import DefaultMigrationIdentityResolver
from pyverge.migrations.json_patch import JsonPatch
from pyverge.migrations.spec import MigrationSpec
from pyverge.registry.errors import (
    CatalogError,
    MigrationConflictError,
    MigrationNotFoundError,
    ModelAlreadyRegisteredError,
    ModelConflictError,
    ModelNotFoundError,
)
from pyverge.versioning import (
    Comparable,
    ContentHasher,
    EdgeEntry,
    EdgeKey,
    Identifiable,
    Migratable,
    ModelRef,
    NodeEntry,
    NodeId,
    Transitional,
    VersionEdge,
    VersionNode,
)
from pyverge.versioning.errors import NodeConflictError

from .linters import HealthLinter
from .types import HealthIssue, ReflectionPort


class Registry(Generic[VersionValue]):
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
            namespace="default",
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
    >>> registry = Registry[semver.Version](
    ...     namespace="default", hasher=default_content_hasher(), linters=()
    ... )
    >>> v1 = adapter.versionable(UserV1)
    >>> v2 = adapter.versionable(UserV2)
    >>> _ = registry.store(v1)
    >>> _ = registry.store(v2)
    >>> registry.get_model(v1).model_id == "tests.UserV1"
    True
    >>> registry.latest("User").model_id == "tests.UserV2"
    True

    Args:
        namespace: Non-empty namespace owned by this registry.
        hasher: Content-hash strategy used to compare migration content and to
            populate the optional content-hash index.
        reflection: Diff-based model reflection and migration binding.
        linters: Callable health rules locked for this registry instance.
        on_missing: Missing-endpoint policy. ``reconstruct_model`` enables
            reflection; ``raise`` is the default.
        index_content_hashes: Build a content-address lookup for migration
            edges. Leave disabled unless reverse content-hash lookup is needed.

    Raises:
        ValueError: The namespace is empty.
    """

    def __init__(  # noqa: PLR0913
        self: Self,
        *,
        namespace: str,
        hasher: ContentHasher,
        reflection: ReflectionPort[VersionValue] | None = None,
        linters: Sequence[HealthLinter],
        on_missing: str = "raise",
        index_content_hashes: bool = False,
    ) -> None:
        if not namespace:
            raise ValueError("Registry namespace must be non-empty")
        self._namespace = namespace
        self._hasher = hasher
        self._index_content_hashes = index_content_hashes
        self._reflection = reflection
        self._on_missing = on_missing
        self._linters = tuple(linters)
        self._health_issues: dict[Any, tuple[HealthIssue, ...]] = {}
        self._issues_by_namespace: dict[str, set[Any]] = {}
        self._references_to: dict[NodeId, set[Any]] = {}
        self._references_by_entity: dict[Any, frozenset[NodeId]] = {}
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
        raise CatalogError(self._namespace, f"Unsupported index type: {type(index)}")

    def __getitem__(self, index: object) -> NodeEntry | EdgeEntry:
        if isinstance(index, Comparable):
            return self.get_entry(index)
        if isinstance(index, Transitional):
            return self.get_edge(EdgeKey.from_pair(*index.key))
        raise CatalogError(self._namespace, f"Unsupported index type: {type(index)}")

    @property
    def versions(self: Self) -> list[VersionNode[VersionValue]]:
        return [entry for entry in self._by_versions if isinstance(entry, VersionNode)]

    @property
    def entries(self: Self) -> list[NodeEntry]:
        return self._by_versions

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
            raise CatalogError(self._namespace, "No versions registered")
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
            entry.modelref
            for entry in self._by_kinds.get(kind, [])
            if isinstance(entry, VersionNode)
        )

    def migrations(self: Self, kind: ModelKind) -> list[Migratable[VersionValue]]:
        return [
            entry
            for entry in self._migrations.get(kind, [])
            if isinstance(entry, VersionEdge)
        ]

    def edges(self: Self, kind: ModelKind) -> list[EdgeEntry]:
        return list(self._migrations.get(kind, []))

    def migrations_of(
        self: Self, key: Comparable[VersionValue]
    ) -> frozenset[Migratable[VersionValue]]:
        return frozenset(
            edge
            for edge in self._edges_by_version.get(key, ())
            if isinstance(edge, VersionEdge)
        )

    def edges_of(self: Self, key: Comparable[VersionValue]) -> frozenset[EdgeEntry]:
        return frozenset(self._edges_by_version.get(key, ()))

    def kind_versions(self: Self, kind: ModelKind) -> list[VersionNode[VersionValue]]:
        return [
            entry
            for entry in self._by_kinds.get(kind, [])
            if isinstance(entry, VersionNode)
        ]

    def kind_entries(self: Self, kind: ModelKind) -> list[NodeEntry]:
        return list(self._by_kinds.get(kind, []))

    def has_model(self: Self, key: Comparable) -> bool:
        idx = bisect.bisect_left(self._by_versions, key)
        return idx < len(self._by_versions) and self._by_versions[idx] == key

    def health(
        self: Self,
        entity: Identifiable,
    ) -> tuple[HealthIssue, ...]:
        """Return health issues for one node or edge.

        Args:
            entity: Node or edge identity to inspect.

        Returns:
            tuple[HealthIssue, ...]: Issues produced by this registry's
                locked health linters.
        """
        return self._health_issues.get(entity, ())

    @property
    def issues_by_entity(self: Self) -> Mapping[Any, tuple[HealthIssue, ...]]:
        """Return the cached issues keyed by entity."""
        return MappingProxyType(dict(self._health_issues))

    @property
    def issues_by_namespace(self: Self) -> Mapping[str, frozenset[Any]]:
        """Return entities with issues keyed by namespace."""
        return MappingProxyType(
            {
                namespace: frozenset(entities)
                for namespace, entities in self._issues_by_namespace.items()
            }
        )

    @property
    def references_to(self: Self) -> Mapping[NodeId, frozenset[Any]]:
        """Return entities that reference each node identity."""
        return MappingProxyType(
            {
                reference: frozenset(entities)
                for reference, entities in self._references_to.items()
            }
        )

    @property
    def health_issues(self: Self) -> tuple[HealthIssue, ...]:
        """Return all cached health issues for the registry."""
        return tuple(
            sorted(
                (issue for issues in self._health_issues.values() for issue in issues),
                key=lambda issue: (str(issue.entity), issue.code),
            )
        )

    def _set_references(
        self: Self,
        entity: Any,
        references: frozenset[NodeId],
    ) -> None:
        for reference in self._references_by_entity.pop(entity, frozenset()):
            bucket = self._references_to.get(reference)
            if bucket is not None:
                bucket.discard(entity)
                if not bucket:
                    del self._references_to[reference]
        if references:
            self._references_by_entity[entity] = references
            for reference in references:
                self._references_to.setdefault(reference, set()).add(entity)

    def _set_health(
        self: Self,
        entity: Any,
        issues: tuple[HealthIssue, ...],
    ) -> None:
        namespace_bucket = self._issues_by_namespace.get(entity.namespace)
        if namespace_bucket is not None:
            namespace_bucket.discard(entity)
            if not namespace_bucket:
                del self._issues_by_namespace[entity.namespace]
        if issues:
            self._health_issues[entity] = issues
            self._issues_by_namespace.setdefault(entity.namespace, set()).add(entity)
        else:
            self._health_issues.pop(entity, None)

    def _drop_entity(self: Self, entity: Any) -> None:
        self._set_health(entity, ())
        self._set_references(entity, frozenset())

    def _refresh_health(self: Self, entities: Any) -> None:
        for entity in set(entities):
            references = frozenset(getattr(entity, "references", ()))
            self._set_references(entity, references)
            issues = tuple(
                issue for linter in self._linters for issue in linter(self, entity)
            )
            self._set_health(entity, issues)

    def _affected_by_node_change(self: Self, entity: Any) -> set[Any]:
        affected = {entity}
        affected.update(self._references_to.get(entity, ()))
        affected.update(self._edges_by_version.get(entity, ()))
        return affected

    def _affected_by_edge_change(self: Self, entity: Any) -> set[Any]:
        return {entity, entity.source, entity.target}

    def _rebuild_health(self: Self) -> None:
        self._health_issues.clear()
        self._issues_by_namespace.clear()
        self._references_to.clear()
        self._references_by_entity.clear()
        entities: list[Any] = list(self._by_versions)
        for edges in self._migrations.values():
            entities.extend(edges)
        self._refresh_health(entities)

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
        raise MigrationNotFoundError(self._namespace, pair)

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
        if not isinstance(edge, VersionEdge):
            raise MigrationNotFoundError(self._namespace, key.key)
        return edge

    def has_hooks(self: Self, key: Transitional[VersionValue]) -> bool:
        return key in self._hooks

    def latest(self: Self, kind: ModelKind) -> VersionNode[VersionValue]:
        versions = self.kind_versions(kind)
        if not versions:
            raise CatalogError(self._namespace, "No versions registered")
        return versions[-1]

    def earliest(self: Self, kind: ModelKind) -> VersionNode[VersionValue]:
        versions = self.kind_versions(kind)
        if not versions:
            raise CatalogError(self._namespace, "No versions registered")
        return versions[0]

    def hooks(self: Self, key: Transitional | None = None) -> list[Attachable]:
        if key is None:
            return list(chain(*self._hooks.values()))
        return self._hooks[key]

    def copy(self: Self) -> "Registry[VersionValue]":
        new = Registry(
            namespace=self._namespace,
            hasher=self._hasher,
            reflection=self._reflection,
            linters=self._linters,
            on_missing=self._on_missing,
            index_content_hashes=self._index_content_hashes,
        )
        new.copy_from(self)
        return new

    def copy_from(self: Self, source: "Registry[VersionValue]") -> None:
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
        self._health_issues = dict(source._health_issues)
        self._issues_by_namespace = {
            namespace: set(entities)
            for namespace, entities in source._issues_by_namespace.items()
        }
        self._references_to = {
            reference: set(entities)
            for reference, entities in source._references_to.items()
        }
        self._references_by_entity = dict(source._references_by_entity)

    def find_edge_by_content_hash(self, value: str) -> EdgeKey[VersionValue] | None:
        if self._content_hash_index is None:
            return None
        return self._content_hash_index.get(value)

    def store(self: Self, entry: NodeEntry) -> NodeEntry:
        """Insert a new node entry; reject duplicates."""
        if self.find_entry(entry) is not None:
            raise ModelAlreadyRegisteredError(
                catalog_name=self._namespace,
                version=entry,
            )
        bisect.insort_left(self._by_versions, entry)
        bisect.insort_left(self._by_kinds[entry.kind], entry)
        if isinstance(entry, VersionNode):
            self._by_models[entry.modelref] = entry
        self._refresh_health(self._affected_by_node_change(entry))
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
                self._namespace,
                f"Cannot reconcile key-only entry {entry}; hydrate it instead",
            )
        try:
            resolved = entry.reconcile(existing)
        except NodeConflictError as error:
            raise ModelConflictError(
                self._namespace,
                entry,
                existing.fields,
                entry.fields,
            ) from error
        if resolved is not existing:
            self.remove_entry(existing)
            return self.store(resolved)
        return existing

    def find_entry(self: Self, key: Comparable) -> NodeEntry | None:
        """Return the stored entry for ``key``, including key-only entries.

        Args:
            key: Comparable identity to look up.

        Returns:
            NodeEntry | None: The matching node entry, or ``None`` when absent.
        """
        idx = bisect.bisect_left(self._by_versions, key)
        if idx < len(self._by_versions) and self._by_versions[idx] == key:
            return self._by_versions[idx]
        return None

    def get_entry(self: Self, key: Comparable) -> NodeEntry:
        if entry := self.find_entry(key):
            return entry
        raise ModelNotFoundError(self._namespace, key.version)

    def has_entry(self: Self, key: Comparable) -> bool:
        return self.find_entry(key) is not None

    def remove_entry(self: Self, entry: NodeEntry) -> None:
        """Remove a node entry and its conditional secondary indexes."""
        affected = self._affected_by_node_change(entry)
        idx = bisect.bisect_left(self._by_versions, entry)
        if idx < len(self._by_versions) and self._by_versions[idx] == entry:
            del self._by_versions[idx]
        kind_entries = self._by_kinds[entry.kind]
        idx = bisect.bisect_left(kind_entries, entry)
        if idx < len(kind_entries) and kind_entries[idx] == entry:
            del kind_entries[idx]
        if isinstance(entry, VersionNode):
            self._by_models.pop(entry.modelref, None)
        self._drop_entity(entry)
        self._refresh_health(affected - {entry})

    def has_edge(self: Self, key: EdgeKey[VersionValue]) -> bool:
        paths = self._migrations.get(key.kind, [])
        idx = bisect.bisect_left(paths, key)
        return idx < len(paths) and paths[idx] == key

    def get_edge(self: Self, key: EdgeKey[VersionValue]) -> EdgeEntry:
        paths = self._migrations.get(key.kind, [])
        idx = bisect.bisect_left(paths, key)
        if idx < len(paths) and paths[idx] == key:
            return paths[idx]
        raise MigrationNotFoundError(self._namespace, key.key)

    def get_model(
        self: Self,
        key: Comparable,
    ) -> VersionNode[VersionValue]:
        entry = self.find_entry(key)
        if isinstance(entry, VersionNode):
            return entry
        raise ModelNotFoundError(self._namespace, key.version)

    def find_model(self: Self, key: Comparable) -> VersionNode[VersionValue] | None:
        """Return the hydrated model for ``key``, ignoring key-only entries.

        Args:
            key: Comparable identity to look up.

        Returns:
            VersionNode[VersionValue] | None: The matching version node, or
                ``None`` when absent or key-only.
        """
        entry = self.find_entry(key)
        return entry if isinstance(entry, VersionNode) else None

    def get_model_by_ref(self: Self, ref: ModelRef) -> VersionNode[VersionValue]:
        if target := self._by_models.get(ref):
            return target
        raise ModelNotFoundError(self._namespace, ref)

    def remove_model(self: Self, key: Comparable) -> None:

        version_idx = bisect.bisect_left(self._by_versions, key)
        kind_idx = bisect.bisect_left(self._by_kinds[key.kind], key)
        if (
            version_idx == len(self._by_versions)
            or self._by_versions[version_idx] != key
        ):
            raise CatalogError(self._namespace, f"Version {key} is not registered")

        affected = self.migrations_of(key)
        if affected:
            pairs = ", ".join(f"{e.source}→{e.target}" for e in sorted(affected))
            raise CatalogError(
                self._namespace,
                f"Cannot remove version {key}: it is referenced by migrations: {pairs}",
            )

        version = self._by_versions[version_idx]
        affected = self._affected_by_node_change(version)

        del self._by_kinds[key.kind][kind_idx]
        modelref = getattr(version, "modelref", None)
        if modelref is not None:
            self._by_models.pop(modelref, None)
        del self._by_versions[version_idx]
        self._drop_entity(version)
        self._refresh_health(affected - {version})

    def remove_model_by_ref(self: Self, ref: ModelRef) -> None:
        if ref not in self._by_models:
            raise ModelNotFoundError(self._namespace, ref)
        self.remove_model(self._by_models[ref])

    def clear_models(self: Self) -> None:
        if self._migrations:
            raise CatalogError(self._namespace, "Clear migrations first")
        self._by_versions.clear()
        self._by_models.clear()
        self._by_kinds.clear()
        self._rebuild_health()

    def delete_kind(self: Self, kind: ModelKind) -> None:  # noqa: C901
        versions = self.kind_versions(kind)
        if not versions:
            return
        version_set = set(versions)
        for version in versions:
            for edge in self.migrations_of(version):
                if edge.source not in version_set or edge.target not in version_set:
                    raise CatalogError(
                        self._namespace,
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

    def _require_reflection(self: Self) -> ReflectionPort[VersionValue]:
        if self._reflection is None:
            raise CatalogError(
                self._namespace,
                "Migration registration requires a reflection port",
            )
        return self._reflection

    def store_migration(  # noqa: C901, PLR0912, PLR0915
        self: Self,
        entry: MigrationSpec | EdgeEntry,
    ) -> MigrationFunc | EdgeEntry:
        """Store a migration request or a direct edge entry.

        A ``MigrationSpec`` is resolved and reflected into an executable edge.
        An ``EdgeEntry`` is stored directly for key-only or imported graph data.

        Args:
            entry: A registration request or an explicit graph edge.

        Returns:
            MigrationFunc | EdgeEntry: The registered callable for an
                executable migration, otherwise the stored edge entry.

        Raises:
            CatalogError: The migration is invalid or non-adjacent.
            MigrationConflictError: Existing migration content differs.
            MigrationNotFoundError: An endpoint is missing.
            ModelNotFoundError: Missing endpoints cannot be reconstructed.
        """
        spec = entry if isinstance(entry, MigrationSpec) else None
        if spec is not None:
            reflection = self._require_reflection()
            v_from, v_to = spec.pair
            if v_from.kind != v_to.kind:
                raise CatalogError(
                    self._namespace,
                    f"Cannot register migration across kinds: "
                    f"{v_from.kind} != {v_to.kind}",
                )
            resolved_from = self.find_model(v_from)
            resolved_to = self.find_model(v_to)
            if resolved_from is None and resolved_to is None:
                raise ModelNotFoundError(self._namespace, v_from.version)
            if resolved_from is None:
                assert resolved_to is not None
                if self._on_missing != "reconstruct_model":
                    raise ModelNotFoundError(self._namespace, v_from.version)
                diff = reflection.diff(resolved_to, v_from, migration=spec.func)
                resolved_from = reflection.reflect(diff)
                self.store(resolved_from)
            if resolved_to is None:
                if self._on_missing != "reconstruct_model":
                    raise ModelNotFoundError(self._namespace, v_to.version)
                diff = reflection.diff(resolved_from, v_to, migration=spec.func)
                resolved_to = reflection.reflect(diff)
                self.store(resolved_to)
            if not self.is_adjacent(EdgeKey.from_pair(resolved_from, resolved_to)):
                raise CatalogError(
                    self._namespace,
                    f"Cannot register migration with skip versions: {v_from}→{v_to}",
                )
            edge: EdgeEntry = VersionEdge(
                source=resolved_from,
                target=resolved_to,
                diff=reflection.diff(resolved_from, resolved_to),
                func=spec.func,
                migration=DefaultMigrationIdentityResolver().resolve(spec.func),
            )
        else:
            assert not isinstance(entry, MigrationSpec)
            edge = entry
            if isinstance(edge, VersionEdge) and any(
                version not in self._by_versions for version in edge.key
            ):
                raise MigrationNotFoundError(self._namespace, edge.key)

        paths = self._migrations[edge.kind]
        idx = bisect.bisect_left(paths, edge)
        if idx < len(paths) and paths[idx] == edge:
            existing = paths[idx]
            if isinstance(edge, VersionEdge) and not isinstance(existing, VersionEdge):
                del paths[idx]
                for endpoint in (existing.source, existing.target):
                    bucket = self._edges_by_version.get(endpoint)
                    if bucket is not None:
                        bucket.discard(existing)
                        if not bucket:
                            del self._edges_by_version[endpoint]
            else:
                if isinstance(existing, VersionEdge) and isinstance(edge, VersionEdge):
                    registered_hash = existing.content_hash(self._hasher)
                    incoming_hash = edge.content_hash(self._hasher)
                    if registered_hash != incoming_hash:
                        raise MigrationConflictError(
                            self._namespace,
                            edge.key,
                            registered_hash=registered_hash,
                            incoming_hash=incoming_hash,
                        )
                if isinstance(existing, VersionEdge):
                    return existing.func
                return existing

        bisect.insort(paths, edge)
        self._edges_by_version[edge.source].add(edge)
        self._edges_by_version[edge.target].add(edge)
        if isinstance(edge, VersionEdge):
            if self._content_hash_index is not None:
                edge_key = EdgeKey.from_version_edge(edge)
                self._content_hash_index[edge.content_hash(self._hasher)] = edge_key
            self._refresh_health(self._affected_by_edge_change(edge))
            return edge.func

        self._refresh_health(self._affected_by_edge_change(edge))
        return edge

    def reflect(
        self: Self,
        anchor: VersionNode[VersionValue],
        target: Comparable[VersionValue],
        migration: JsonPatch | MigrationFunc,
    ) -> VersionNode[VersionValue]:
        """Reflect a missing model endpoint from an anchor and migration.

        Args:
            anchor: Existing endpoint used to build the diff.
            target: Missing endpoint identity.
            migration: Migration callable describing the transition.

        Returns:
            VersionNode[VersionValue]: The reflected version node.

        Raises:
            ModelNotFoundError: Missing-model reflection is disabled.
        """
        if self._on_missing != "reconstruct_model":
            raise ModelNotFoundError(self._namespace, target.version)
        reflection = self._require_reflection()
        diff = reflection.diff(anchor, target, migration=migration)
        return reflection.reflect(diff)

    def bind(
        self: Self,
        source: VersionNode[VersionValue],
        target: VersionNode[VersionValue],
    ) -> Any:
        """Bind a migration artifact from the diff between two models.

        Args:
            source: Source model.
            target: Target model.

        Returns:
            Any: The bound migration artifact.

        Raises:
            CatalogError: The endpoints are incompatible for binding.
        """
        if source.kind != target.kind:
            raise CatalogError(
                self._namespace,
                f"Cannot bind migration across kinds: {source.kind} != {target.kind}",
            )
        if source.strategy != target.strategy:
            raise CatalogError(
                self._namespace,
                f"Cannot bind migration across strategies: "
                f"{source.strategy.__name__} != {target.strategy.__name__}",
            )
        reflection = self._require_reflection()
        return reflection.bind(reflection.diff(source, target))

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
                self._namespace,
                f"Cannot remove migration {key}: "
                "it has registered hooks. Clear hooks first.",
            )

        idx = bisect.bisect_left(self._migrations[key.kind], key)
        existing = None
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
        if existing is not None:
            affected = self._affected_by_edge_change(existing)
            self._drop_entity(existing)
            self._refresh_health(affected - {existing})
        else:
            self._refresh_health({key, key.source, key.target})

    def clear_migrations(self: Self) -> None:
        self.clear_hooks()
        self._migrations.clear()
        self._edges_by_version.clear()
        if self._content_hash_index is not None:
            self._content_hash_index.clear()
        self._rebuild_health()

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
                raise CatalogError(self._namespace, msg)
            if self.has_hooks(edge_key):
                raise CatalogError(
                    self._namespace,
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
        self._refresh_health({key})

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
            raise CatalogError(
                self._namespace, f"No hooks registered for migration {key}"
            )

        if hook is None:
            del self._hooks[key]
        elif hook in self._hooks[key]:
            self._hooks[key].remove(hook)
            if not self._hooks[key]:
                del self._hooks[key]
        else:
            raise ValueError(f"Hook {hook!r} is not registered for migration {key}")
        self._refresh_health({key})

    def clear_hooks(
        self: Self,
        key: Transitional[VersionValue] | None = None,
    ) -> None:
        if key is None:
            [hooks.clear() for hooks in self._hooks.values()]
            self._hooks.clear()

        if key is not None and key not in self._hooks:
            raise CatalogError(
                self._namespace, f"No hooks registered for migration {key}"
            )

        if key is None:
            [hooks.clear() for hooks in self._hooks.values()]
            self._hooks.clear()
        else:
            self._hooks[key].clear()
            del self._hooks[key]
