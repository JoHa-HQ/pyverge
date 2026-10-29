from __future__ import annotations

import bisect
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from itertools import chain
from types import MappingProxyType
from typing import Any, Generic, cast

from pyverge.core.types import Attachable, ModelKind, VersionValue
from pyverge.registry.errors import (
    CatalogError,
    MigrationNotFoundError,
    MigrationPathError,
    ModelNotFoundError,
)
from pyverge.registry.memory import InMemoryCatalog
from pyverge.versioning import (
    Comparable,
    EdgeEntry,
    EdgeKey,
    Migratable,
    ModelRef,
    NodeEntry,
    NodeId,
    Transitional,
    VersionNode,
)


def _freeze(values: Mapping[Any, Any]) -> Mapping[Any, Any]:
    return MappingProxyType(dict(values))


@dataclass(frozen=True, slots=True)
class MigrationGraph(Generic[VersionValue]):
    """Immutable graph snapshot compiled from a mutable registry."""

    name: str
    namespace: str
    nodes: tuple[NodeEntry, ...]
    nodes_by_kind: Mapping[ModelKind, tuple[NodeEntry, ...]]
    models_by_ref: Mapping[ModelRef, VersionNode[VersionValue]]
    edges_by_kind: Mapping[ModelKind, tuple[EdgeEntry, ...]]
    edges_by_endpoint: Mapping[NodeId, frozenset[EdgeEntry]]
    hooks_by_edge: Mapping[EdgeKey, tuple[Attachable, ...]]
    content_hashes: Mapping[str, EdgeKey]

    @classmethod
    def from_catalog(
        cls,
        catalog: InMemoryCatalog[VersionValue],
    ) -> MigrationGraph[VersionValue]:
        nodes = tuple(catalog.entries)
        kinds = set(catalog.entities) | set(catalog.kinds)
        nodes_by_kind = {kind: tuple(catalog.kind_entries(kind)) for kind in kinds}
        edges_by_kind = {kind: tuple(catalog.edges(kind)) for kind in kinds}
        edges_by_endpoint: dict[NodeId, set[EdgeEntry]] = defaultdict(set)
        hooks_by_edge: dict[EdgeKey, tuple[Attachable, ...]] = {}
        for edges in edges_by_kind.values():
            for edge in edges:
                key = EdgeKey.from_pair(*edge.key)
                edges_by_endpoint[edge.source].add(edge)
                edges_by_endpoint[edge.target].add(edge)
                registered_hooks = catalog.get_hooks(key)
                if registered_hooks:
                    hooks_by_edge[key] = tuple(registered_hooks)
        content_hashes = dict(catalog.content_hashes)
        return cls(
            name=catalog.name,
            namespace=catalog.namespace,
            nodes=nodes,
            nodes_by_kind=_freeze(nodes_by_kind),
            models_by_ref=_freeze(
                {ref: catalog.get_model_by_ref(ref) for ref in catalog.models(None)}
            ),
            edges_by_kind=_freeze(edges_by_kind),
            edges_by_endpoint=_freeze(
                {
                    endpoint: frozenset(edges)
                    for endpoint, edges in edges_by_endpoint.items()
                }
            ),
            hooks_by_edge=_freeze(hooks_by_edge),
            content_hashes=_freeze(content_hashes),
        )

    @property
    def entries(self) -> tuple[NodeEntry, ...]:
        return self.nodes

    @property
    def versions(self) -> list[VersionNode[VersionValue]]:
        return [
            cast("VersionNode[VersionValue]", node)
            for node in self.nodes
            if node.is_model
        ]

    def versions_for(
        self, kind: ModelKind | None = None
    ) -> list[VersionNode[VersionValue]]:
        if kind is None:
            return self.versions
        return self.kind_versions(kind)

    def kinds(self) -> list[ModelKind]:
        return sorted(self.nodes_by_kind)

    @property
    def entities(self) -> list[ModelKind]:
        return [kind for kind, nodes in self.nodes_by_kind.items() if nodes]

    def models(self, kind: ModelKind | None) -> frozenset[ModelRef]:
        if kind is None:
            return frozenset(self.models_by_ref)
        return frozenset(
            cast("ModelRef", node.modelref)
            for node in self.nodes_by_kind.get(kind, ())
            if node.modelref is not None
        )

    def kind_versions(self, kind: ModelKind) -> list[VersionNode[VersionValue]]:
        return [
            cast("VersionNode[VersionValue]", node)
            for node in self.nodes_by_kind.get(kind, ())
            if node.is_model
        ]

    def kind_entries(self, kind: ModelKind) -> list[NodeEntry]:
        return list(self.nodes_by_kind.get(kind, ()))

    def has_model(self, key: Comparable) -> bool:
        return self.find_model(key) is not None

    def has_entry(self, key: Comparable) -> bool:
        return self.find_entry(key) is not None

    def find_entry(self, key: Comparable) -> NodeEntry | None:
        idx = bisect.bisect_left(self.nodes, key)
        if idx < len(self.nodes) and self.nodes[idx] == key:
            return self.nodes[idx]
        return None

    def get_entry(self, key: Comparable) -> NodeEntry:
        if entry := self.find_entry(key):
            return entry
        raise ModelNotFoundError(self.name, key.version)

    def find_model(self, key: Comparable) -> VersionNode[VersionValue] | None:
        entry = self.find_entry(key)
        return (
            cast("VersionNode[VersionValue]", entry)
            if entry and entry.is_model
            else None
        )

    def get_model(self, key: Comparable) -> VersionNode[VersionValue]:
        model = self.find_model(key)
        if model is None:
            raise ModelNotFoundError(self.name, key.version)
        return model

    def get_model_by_ref(self, ref: ModelRef) -> VersionNode[VersionValue]:
        model = self.models_by_ref.get(ref)
        if model is None:
            raise ModelNotFoundError(self.name, ref)
        return model

    def latest(self, kind: ModelKind) -> VersionNode[VersionValue]:
        versions = self.kind_versions(kind)
        if not versions:
            raise CatalogError(self.name, "No versions registered")
        return versions[-1]

    def earliest(self, kind: ModelKind) -> VersionNode[VersionValue]:
        versions = self.kind_versions(kind)
        if not versions:
            raise CatalogError(self.name, "No versions registered")
        return versions[0]

    @property
    def latest_version(self) -> VersionNode[VersionValue]:
        versions = self.versions
        if not versions:
            raise CatalogError(self.name, "No versions registered")
        return versions[-1]

    def missing_references(
        self,
        node: VersionNode[VersionValue],
        *,
        require_registered: bool = True,
    ) -> frozenset[NodeId]:
        registered = (
            self.get_model(node)
            if require_registered
            else self.find_model(node) or node
        )
        missing = []
        for reference in registered.references:
            resolved = reference
            if not resolved.namespace and self.namespace:
                resolved = NodeId(
                    namespace=self.namespace,
                    kind=resolved.kind,
                    version=resolved.version,
                )
            if not self.has_model(resolved):
                missing.append(resolved)
        return frozenset(missing)

    def migrations(self, kind: ModelKind) -> list[Migratable[VersionValue]]:
        return [
            cast("Migratable[VersionValue]", edge)
            for edge in self.edges_by_kind.get(kind, ())
            if edge.is_executable
        ]

    def edges(self, kind: ModelKind) -> list[EdgeEntry]:
        return list(self.edges_by_kind.get(kind, ()))

    def migrations_of(
        self, key: Comparable[VersionValue]
    ) -> frozenset[Migratable[VersionValue]]:
        return frozenset(
            cast("Migratable[VersionValue]", edge)
            for edge in self.edges_by_endpoint.get(key.id, frozenset())
            if edge.is_executable
        )

    def edges_of(self, key: Comparable[VersionValue]) -> frozenset[EdgeEntry]:
        return self.edges_by_endpoint.get(key.id, frozenset())

    def _find_edge(
        self,
        kind: ModelKind,
        pair: tuple[NodeId, NodeId],
    ) -> EdgeEntry:
        key = EdgeKey.from_pair(*pair)
        idx = bisect.bisect_left(self.edges_by_kind.get(kind, ()), key)
        edges = self.edges_by_kind.get(kind, ())
        if idx < len(edges) and edges[idx].key == pair:
            return edges[idx]
        raise MigrationNotFoundError(self.name, pair)

    def has_migration(self, key: Transitional[VersionValue]) -> bool:
        try:
            return self._find_edge(key.kind, key.key).is_executable
        except MigrationNotFoundError:
            return False

    def has_edge(self, key: EdgeKey[VersionValue]) -> bool:
        try:
            self._find_edge(key.kind, key.key)
            return True
        except MigrationNotFoundError:
            return False

    def get_migration(
        self, key: Transitional[VersionValue]
    ) -> Migratable[VersionValue]:
        return self.get_migration_by_edge(key)

    def get_edge(self, key: EdgeKey[VersionValue]) -> EdgeEntry:
        return self._find_edge(key.kind, key.key)

    def get_migration_by_edge(
        self,
        key: Transitional[VersionValue],
    ) -> Migratable[VersionValue]:
        edge = self._find_edge(key.kind, key.key)
        if not edge.is_executable:
            raise MigrationNotFoundError(self.name, key.key)
        return cast("Migratable[VersionValue]", edge)

    def is_adjacent(self, key: Transitional[VersionValue]) -> bool:
        nodes = self.nodes_by_kind.get(key.kind, ())
        from_idx = bisect.bisect_left(nodes, key.source)
        to_idx = bisect.bisect_left(nodes, key.target)
        return abs(from_idx - to_idx) == 1

    def is_critical_edge(self, key: Transitional[VersionValue]) -> bool:
        edges = self.edges_by_kind.get(key.kind, ())
        idx = bisect.bisect_left(edges, key)
        return len(edges) > 2 and (idx > 0 or idx < len(edges) - 1)  # noqa: PLR2004

    def has_hooks(self, key: Transitional[VersionValue]) -> bool:
        return EdgeKey.from_pair(*key.key) in self.hooks_by_edge

    def hooks(self, key: Transitional[VersionValue] | None = None) -> list[Attachable]:
        if key is None:
            return list(chain.from_iterable(self.hooks_by_edge.values()))
        return list(self.hooks_by_edge.get(EdgeKey.from_pair(*key.key), ()))

    def get_hooks(self, key: Transitional[VersionValue]) -> list[Attachable]:
        return self.hooks(key)

    def find_edge_by_content_hash(self, value: str) -> EdgeKey | None:
        return self.content_hashes.get(value)

    def migration_path(
        self,
        from_version: Comparable[VersionValue],
        to_version: Comparable[VersionValue],
    ) -> list[tuple[VersionNode[VersionValue], VersionNode[VersionValue]]]:
        if from_version.kind != to_version.kind:
            raise CatalogError(
                self.name,
                f"Cannot find path across kinds: "
                f"{from_version.kind} != {to_version.kind}",
            )
        kind_versions = self.kind_versions(from_version.kind)
        if from_version not in kind_versions:
            raise MigrationPathError(
                self.name,
                from_version,
                to_version,
                f"Version {from_version} is not registered",
            )
        if to_version not in kind_versions:
            raise MigrationPathError(self.name, (from_version, to_version))
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
                    self.name,
                    current,
                    nxt,
                    f"No migration key is found ({current}, {nxt})",
                )
        return path

    def path(self, source: Any, target: Any) -> list[Any]:
        return self.migration_path(source, target)


__all__ = ["MigrationGraph"]
