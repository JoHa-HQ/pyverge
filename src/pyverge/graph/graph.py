from __future__ import annotations

import bisect
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Generic, cast

from pyverge.core.types import ModelKind, VersionValue
from pyverge.registry.errors import (
    CatalogError,
    MigrationNotFoundError,
    MigrationPathError,
    ModelNotFoundError,
)
from pyverge.versioning import (
    Comparable,
    EdgeKey,
    ModelRef,
    NodeEntry,
    NodeId,
    Transitional,
    VersionNode,
)


@dataclass(frozen=True, slots=True)
class MigrationGraph(Generic[VersionValue]):
    """Immutable graph snapshot compiled from a mutable registry.

    The graph stores edge identity only.  Executable migration bindings and
    hooks live in an execution-side :class:`MigrationResolver`.
    """

    name: str
    namespace: str
    nodes: tuple[NodeEntry, ...]
    nodes_by_kind: Mapping[ModelKind, tuple[NodeEntry, ...]]
    models_by_ref: Mapping[ModelRef, VersionNode[VersionValue]]
    edges_by_kind: Mapping[ModelKind, tuple[EdgeKey, ...]]
    edges_by_endpoint: Mapping[NodeId, frozenset[EdgeKey]]
    executable_edges: frozenset[EdgeKey]
    edge_metadata: Mapping[EdgeKey, Mapping[str, str]]
    content_hashes: Mapping[str, EdgeKey]

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

    @property
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

    def migrations(self, kind: ModelKind) -> list[EdgeKey[VersionValue]]:
        return [
            edge
            for edge in self.edges_by_kind.get(kind, ())
            if edge in self.executable_edges
        ]

    def edges(self, kind: ModelKind) -> list[EdgeKey[VersionValue]]:
        return list(self.edges_by_kind.get(kind, ()))

    def migrations_of(
        self, key: Comparable[VersionValue]
    ) -> frozenset[EdgeKey[VersionValue]]:
        return frozenset(
            edge
            for edge in self.edges_by_endpoint.get(key.id, frozenset())
            if edge in self.executable_edges
        )

    def edges_of(
        self, key: Comparable[VersionValue]
    ) -> frozenset[EdgeKey[VersionValue]]:
        return frozenset(self.edges_by_endpoint.get(key.id, frozenset()))

    def _find_edge(
        self,
        kind: ModelKind,
        pair: tuple[NodeId, NodeId],
    ) -> EdgeKey[VersionValue]:
        key = EdgeKey.from_pair(*pair)
        idx = bisect.bisect_left(self.edges_by_kind.get(kind, ()), key)
        edges = self.edges_by_kind.get(kind, ())
        if idx < len(edges) and edges[idx].key == pair:
            return edges[idx]
        raise MigrationNotFoundError(self.name, pair)

    def has_migration(self, key: Transitional[VersionValue]) -> bool:
        try:
            edge = self._find_edge(key.kind, key.key)
        except MigrationNotFoundError:
            return False
        return edge in self.executable_edges

    def has_edge(self, key: EdgeKey[VersionValue]) -> bool:
        try:
            self._find_edge(key.kind, key.key)
            return True
        except MigrationNotFoundError:
            return False

    def get_migration(self, key: Transitional[VersionValue]) -> EdgeKey[VersionValue]:
        return self.get_migration_by_edge(key)

    def get_edge(self, key: EdgeKey[VersionValue]) -> EdgeKey[VersionValue]:
        return self._find_edge(key.kind, key.key)

    def get_migration_by_edge(
        self,
        key: Transitional[VersionValue],
    ) -> EdgeKey[VersionValue]:
        edge = self._find_edge(key.kind, key.key)
        if edge not in self.executable_edges:
            raise MigrationNotFoundError(self.name, key.key)
        return edge

    def is_adjacent(self, key: Transitional[VersionValue]) -> bool:
        nodes = self.nodes_by_kind.get(key.kind, ())
        from_idx = bisect.bisect_left(nodes, key.source)
        to_idx = bisect.bisect_left(nodes, key.target)
        return abs(from_idx - to_idx) == 1

    def is_critical_edge(self, key: Transitional[VersionValue]) -> bool:
        edges = self.edges_by_kind.get(key.kind, ())
        idx = bisect.bisect_left(edges, key)
        return len(edges) > 2 and (idx > 0 or idx < len(edges) - 1)  # noqa: PLR2004

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
