from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Literal, Protocol, runtime_checkable

from pyverge.core.types import ModelKind, VersionValue
from pyverge.core.versioning import (
    EdgeId,
    EdgeKey,
    ModelRef,
    NodeEntry,
    NodeId,
    VersionNode,
)

Direction = Literal["out", "in", "both"]
"""Traversal direction for backend neighbor queries."""

EdgePredicate = Callable[[EdgeKey], bool]
"""Predicate used to filter edges during backend traversal."""


class GraphCycleError(ValueError):
    """Raised when a backend traversal requires an acyclic graph."""


@runtime_checkable
class GraphBackend(Protocol[VersionValue]):
    """Backend-neutral port over a locked graph.

    A backend owns its own state and indexes. The protocol exposes only
    neutral values: native ``NodeEntry`` and ``EdgeKey`` payloads plus stable
    IDs. No backend-native node or edge object leaks through.
    """

    @property
    def name(self) -> str: ...

    @property
    def namespace(self) -> str: ...

    @property
    def nodes(self) -> tuple[NodeEntry, ...]: ...

    @property
    def edges(self) -> tuple[EdgeKey, ...]: ...

    @property
    def nodes_by_id(self) -> Mapping[NodeId, NodeEntry]: ...

    @property
    def edges_by_id(self) -> Mapping[EdgeId, EdgeKey]: ...

    @property
    def nodes_by_kind(self) -> Mapping[ModelKind, tuple[NodeEntry, ...]]: ...

    @property
    def edges_by_kind(self) -> Mapping[ModelKind, tuple[EdgeKey, ...]]: ...

    @property
    def edges_by_endpoint(self) -> Mapping[NodeId, frozenset[EdgeKey]]: ...

    @property
    def models_by_ref(self) -> Mapping[ModelRef, VersionNode[VersionValue]]: ...

    @property
    def executable_edge_ids(self) -> frozenset[EdgeId]: ...

    @property
    def executable_edges(self) -> frozenset[EdgeKey]: ...

    @property
    def edge_metadata(self) -> Mapping[EdgeId, Mapping[str, str]]: ...

    @property
    def content_hashes(self) -> Mapping[str, EdgeId]: ...

    def edge_key(self, edge: EdgeId) -> EdgeKey: ...

    def is_executable(self, edge: EdgeId) -> bool: ...

    def nodes_for_kind(self, kind: ModelKind) -> tuple[NodeEntry, ...]: ...

    def edges_for_kind(self, kind: ModelKind) -> tuple[EdgeKey, ...]: ...

    def incident(self, node: NodeId) -> frozenset[EdgeKey]: ...

    def outgoing(self, node: NodeId) -> frozenset[EdgeKey]: ...

    def incoming(self, node: NodeId) -> frozenset[EdgeKey]: ...

    def edges_between(
        self,
        source: NodeId,
        target: NodeId,
    ) -> tuple[EdgeKey, ...]: ...

    def has_node(self, node: NodeId) -> bool: ...

    def has_edge(self, edge: EdgeId) -> bool: ...

    def neighbors(
        self,
        node: NodeId,
        *,
        direction: Direction = "both",
    ) -> tuple[NodeId, ...]: ...

    def index_of(self, node: NodeId) -> int | None: ...

    def shortest_path(
        self,
        source: NodeId,
        target: NodeId,
        *,
        predicate: EdgePredicate | None = None,
    ) -> tuple[EdgeKey, ...] | None: ...

    def topological_sort(self) -> tuple[NodeId, ...]: ...


__all__ = [
    "Direction",
    "EdgePredicate",
    "GraphBackend",
    "GraphCycleError",
]
