from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Generic, cast

from pyverge.core.registry.errors import (
    CatalogError,
    MigrationNotFoundError,
    MigrationPathError,
    ModelNotFoundError,
)
from pyverge.core.types import ModelKind, VersionValue
from pyverge.core.versioning import (
    DEFAULT_DISCRIMINATOR,
    Comparable,
    EdgeId,
    EdgeKey,
    ModelRef,
    NodeEntry,
    NodeId,
    Transitional,
    VersionNode,
)

from .backend import GraphBackend
from .state import GraphState


@dataclass(frozen=True, slots=True)
class MigrationGraph(Generic[VersionValue]):
    """Immutable graph snapshot compiled from a mutable registry.

    The graph stores edge identity only. Executable migration bindings and
    hooks live in the runtime binding layer. Traversal is delegated to the
    backend held by :class:`GraphState`.
    """

    state: GraphState[VersionValue]

    @property
    def name(self) -> str:
        return self.state.name

    @property
    def namespace(self) -> str:
        return self.state.namespace

    @property
    def backend(self) -> GraphBackend[VersionValue]:
        return self.state.backend

    @property
    def entries(self) -> tuple[NodeEntry, ...]:
        return self.state.backend.nodes

    @property
    def nodes(self) -> tuple[NodeEntry, ...]:
        return self.state.backend.nodes

    @property
    def nodes_by_kind(self) -> Mapping[ModelKind, tuple[NodeEntry, ...]]:
        return self.state.backend.nodes_by_kind

    @property
    def edges_by_kind(self) -> Mapping[ModelKind, tuple[EdgeKey, ...]]:
        return self.state.backend.edges_by_kind

    @property
    def edges_by_endpoint(self) -> Mapping[NodeId, frozenset[EdgeKey]]:
        return self.state.backend.edges_by_endpoint

    @property
    def models_by_ref(self) -> Mapping[ModelRef, VersionNode[VersionValue]]:
        return self.state.models_by_ref

    @property
    def executable_edge_ids(self) -> frozenset[EdgeId]:
        return self.state.executable_edge_ids

    @property
    def executable_edges(self) -> frozenset[EdgeKey]:
        return self.state.executable_edges

    @property
    def edge_metadata(self) -> Mapping[EdgeId, Mapping[str, str]]:
        return self.state.edge_metadata

    @property
    def content_hashes(self) -> Mapping[str, EdgeKey]:
        return MappingProxyType(
            {
                digest: self.state.edges[edge_id]
                for digest, edge_id in self.state.content_hashes.items()
            }
        )

    @property
    def versions(self) -> list[VersionNode[VersionValue]]:
        return [
            cast("VersionNode[VersionValue]", node)
            for node in self.state.backend.nodes
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
        return sorted(
            set(self.state.backend.nodes_by_kind)
            | set(self.state.backend.edges_by_kind)
        )

    @property
    def entities(self) -> list[ModelKind]:
        return [
            kind
            for kind in self.kinds
            if self.state.backend.nodes_for_kind(kind)
        ]

    def models(self, kind: ModelKind | None) -> frozenset[ModelRef]:
        if kind is None:
            return frozenset(self.state.models_by_ref)
        return frozenset(
            cast("ModelRef", node.modelref)
            for node in self.state.backend.nodes_for_kind(kind)
            if node.modelref is not None
        )

    def kind_versions(self, kind: ModelKind) -> list[VersionNode[VersionValue]]:
        return [
            cast("VersionNode[VersionValue]", node)
            for node in self.state.backend.nodes_for_kind(kind)
            if node.is_model
        ]

    def kind_entries(self, kind: ModelKind) -> list[NodeEntry]:
        return list(self.state.backend.nodes_for_kind(kind))

    def has_model(self, key: Comparable) -> bool:
        return self.find_model(key) is not None

    def has_entry(self, key: Comparable) -> bool:
        return self.find_entry(key) is not None

    def find_entry(self, key: Comparable) -> NodeEntry | None:
        return self.state.nodes.get(key.id)

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
        model = self.state.models_by_ref.get(ref)
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

    def migrations(self, kind: ModelKind) -> list[EdgeKey[VersionValue]]:
        return [
            edge
            for edge in self.state.backend.edges_for_kind(kind)
            if edge.id in self.state.executable_edge_ids
        ]

    def edges(self, kind: ModelKind) -> list[EdgeKey[VersionValue]]:
        return list(self.state.backend.edges_for_kind(kind))

    def migrations_of(
        self, key: Comparable[VersionValue]
    ) -> frozenset[EdgeKey[VersionValue]]:
        return frozenset(
            edge
            for edge in self.state.backend.incident(key.id)
            if edge.id in self.state.executable_edge_ids
        )

    def edges_of(
        self, key: Comparable[VersionValue]
    ) -> frozenset[EdgeKey[VersionValue]]:
        return frozenset(self.state.backend.incident(key.id))

    def node_entries(
        self,
        *,
        full: bool | None = None,
        connected: bool | None = None,
        orphaned: bool | None = None,
    ) -> tuple[NodeEntry, ...]:
        """Return node entries filtered by lookup flags."""
        entries: list[NodeEntry] = []
        for entry in self.state.backend.nodes:
            is_full = entry.is_model
            is_connected = bool(self.state.backend.incident(entry.id))
            if full is not None and is_full != full:
                continue
            if connected is not None and is_connected != connected:
                continue
            if orphaned is not None and (not is_connected) != orphaned:
                continue
            entries.append(entry)
        return tuple(entries)

    def edge_entries(
        self,
        *,
        kind: ModelKind | None = None,
        executable: bool | None = None,
        origin: str | None = None,
    ) -> tuple[EdgeKey[VersionValue], ...]:
        """Return edge entries filtered by lookup flags."""
        edges = (
            self.state.backend.edges
            if kind is None
            else self.state.backend.edges_for_kind(kind)
        )
        entries: list[EdgeKey[VersionValue]] = []
        for edge in edges:
            is_executable = edge.id in self.state.executable_edge_ids
            if executable is not None and is_executable != executable:
                continue
            if origin is not None:
                metadata = self.state.edge_metadata.get(edge.id, {})
                if metadata.get("origin") != origin:
                    continue
            entries.append(edge)
        return tuple(entries)

    def _find_edge(
        self,
        pair: tuple[NodeId, NodeId],
        discriminator: str = DEFAULT_DISCRIMINATOR,
    ) -> EdgeKey[VersionValue]:
        source, target = pair
        for edge in self.state.backend.edges_between(source, target):
            if edge.discriminator == discriminator:
                return edge
        raise MigrationNotFoundError(self.name, pair)

    def has_migration(self, key: Transitional[VersionValue]) -> bool:
        edge = self.state.edges.get(key.id)
        return (
            edge is not None
            and edge.id in self.state.executable_edge_ids
        )

    def has_edge(self, key: EdgeKey[VersionValue]) -> bool:
        return self.state.backend.has_edge(key)

    def get_migration(self, key: Transitional[VersionValue]) -> EdgeKey[VersionValue]:
        return self.get_migration_by_edge(key)

    def get_edge(self, key: EdgeKey[VersionValue]) -> EdgeKey[VersionValue]:
        edge = self.state.edges.get(key.id)
        if edge is None:
            raise MigrationNotFoundError(self.name, key.key)
        return edge

    def get_migration_by_edge(
        self,
        key: Transitional[VersionValue],
    ) -> EdgeKey[VersionValue]:
        edge = self.state.edges.get(key.id)
        if edge is None or edge.id not in self.state.executable_edge_ids:
            raise MigrationNotFoundError(self.name, key.key)
        return edge

    def is_adjacent(self, key: Transitional[VersionValue]) -> bool:
        from_idx = self.state.backend.index_of(key.source)
        to_idx = self.state.backend.index_of(key.target)
        if from_idx is None or to_idx is None:
            return False
        return abs(from_idx - to_idx) == 1

    def is_critical_edge(self, key: Transitional[VersionValue]) -> bool:
        edges = self.state.backend.edges_for_kind(key.kind)
        idx = next(
            (index for index, edge in enumerate(edges) if edge == key),
            None,
        )
        if idx is None:
            return False
        return len(edges) > 2 and (idx > 0 or idx < len(edges) - 1)  # noqa: PLR2004

    def find_edge_by_content_hash(self, value: str) -> EdgeKey | None:
        edge_id = self.state.content_hashes.get(value)
        if edge_id is None:
            return None
        return self.state.edges.get(edge_id)

    def edge_path(
        self,
        from_version: Comparable[VersionValue],
        to_version: Comparable[VersionValue],
        *,
        discriminator: str = DEFAULT_DISCRIMINATOR,
    ) -> list[EdgeKey[VersionValue]]:
        """Resolve the adjacent edge walk between two graph versions."""
        if from_version.kind != to_version.kind:
            raise CatalogError(
                self.name,
                f"Cannot find path across kinds: "
                f"{from_version.kind} != {to_version.kind}",
            )
        versions = self.kind_versions(from_version.kind)
        positions = {
            cast("NodeId", node.id): index
            for index, node in enumerate(versions)
        }
        lo = positions.get(from_version.id)
        hi = positions.get(to_version.id)
        if lo is None:
            raise MigrationPathError(
                self.name,
                from_version,
                to_version,
                f"Version {from_version} is not registered",
            )
        if hi is None:
            raise MigrationPathError(self.name, (from_version, to_version))
        if lo == hi:
            return []
        step = 1 if lo < hi else -1
        path: list[EdgeKey[VersionValue]] = []
        current = versions[lo]
        while lo != hi:
            next_index = lo + step
            target = versions[next_index]
            try:
                edge = self._find_edge((current.id, target.id), discriminator)
            except MigrationNotFoundError:
                raise MigrationPathError(
                    self.name,
                    current,
                    target,
                    f"No migration key is found ({current}, {target})",
                ) from None
            if edge.id not in self.state.executable_edge_ids:
                raise MigrationPathError(
                    self.name,
                    current,
                    target,
                    f"No migration key is found ({current}, {target})",
                )
            path.append(edge)
            current = target
            lo = next_index
        return path

    def migration_path(
        self,
        from_version: Comparable[VersionValue],
        to_version: Comparable[VersionValue],
    ) -> list[tuple[VersionNode[VersionValue], VersionNode[VersionValue]]]:
        return [
            (
                cast("VersionNode[VersionValue]", edge.source),
                cast("VersionNode[VersionValue]", edge.target),
            )
            for edge in self.edge_path(from_version, to_version)
        ]

    def path(self, source: Any, target: Any) -> list[Any]:
        return self.migration_path(source, target)

__all__ = ["MigrationGraph"]
