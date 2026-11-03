from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Generic, Literal, Protocol, runtime_checkable

from pyverge.core.types import ModelKind, VersionValue, VersionValue_co
from pyverge.core.versioning import EdgeId, EdgeKey, NodeEntry, NodeId

Direction = Literal["out", "in", "both"]
"""Traversal direction for backend neighbor queries."""

EdgePredicate = Callable[[EdgeKey], bool]
"""Predicate used to filter edges during backend traversal."""


class GraphCycleError(ValueError):
    """Raised when a backend traversal requires an acyclic graph."""


@runtime_checkable
class GraphBackend(Protocol[VersionValue_co]):
    """Backend-neutral port over a locked graph.

    Backends store native ``NodeEntry`` and ``EdgeKey`` values, or stable IDs
    for traversal. No backend-native node or edge object is exposed.
    """

    @property
    def nodes(self) -> tuple[NodeEntry, ...]: ...

    @property
    def edges(self) -> tuple[EdgeKey, ...]: ...

    @property
    def nodes_by_kind(self) -> Mapping[ModelKind, tuple[NodeEntry, ...]]: ...

    @property
    def edges_by_kind(self) -> Mapping[ModelKind, tuple[EdgeKey, ...]]: ...

    @property
    def edges_by_endpoint(self) -> Mapping[NodeId, frozenset[EdgeKey]]: ...

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


@dataclass(frozen=True, slots=True)
class IndexedBackend(Generic[VersionValue]):
    """Dependency-free backend using frozen maps and sorted tuples."""

    nodes: tuple[NodeEntry, ...]
    edges: tuple[EdgeKey, ...]
    nodes_by_id: Mapping[NodeId, NodeEntry]
    nodes_by_kind: Mapping[ModelKind, tuple[NodeEntry, ...]]
    edges_by_kind: Mapping[ModelKind, tuple[EdgeKey, ...]]
    edges_by_endpoint: Mapping[NodeId, frozenset[EdgeKey]]
    outgoing_by_node: Mapping[NodeId, frozenset[EdgeKey]]
    incoming_by_node: Mapping[NodeId, frozenset[EdgeKey]]
    edges_by_pair: Mapping[tuple[NodeId, NodeId], tuple[EdgeKey, ...]]
    node_positions: Mapping[NodeId, int]
    edge_ids: frozenset[EdgeId]

    @classmethod
    def build(
        cls,
        nodes: Iterable[NodeEntry],
        edges: Iterable[EdgeKey],
    ) -> IndexedBackend:
        ordered_nodes = tuple(sorted(nodes))
        ordered_edges = tuple(sorted(edges))

        nodes_by_kind: dict[ModelKind, list[NodeEntry]] = {}
        node_positions: dict[NodeId, int] = {}
        for entry in ordered_nodes:
            bucket = nodes_by_kind.setdefault(entry.kind, [])
            node_positions[entry.id] = len(bucket)
            bucket.append(entry)

        edges_by_kind: dict[ModelKind, list[EdgeKey]] = {}
        edges_by_endpoint: dict[NodeId, set[EdgeKey]] = {}
        outgoing: dict[NodeId, set[EdgeKey]] = {}
        incoming: dict[NodeId, set[EdgeKey]] = {}
        edges_by_pair: dict[tuple[NodeId, NodeId], list[EdgeKey]] = {}
        edge_ids: set[EdgeId] = set()
        for edge in ordered_edges:
            edges_by_kind.setdefault(edge.kind, []).append(edge)
            edge_ids.add(edge.id)
            for endpoint in (edge.source.id, edge.target.id):
                edges_by_endpoint.setdefault(endpoint, set()).add(edge)
            outgoing.setdefault(edge.source.id, set()).add(edge)
            incoming.setdefault(edge.target.id, set()).add(edge)
            edges_by_pair.setdefault(edge.key, []).append(edge)

        return cls(
            nodes=ordered_nodes,
            edges=ordered_edges,
            nodes_by_id=MappingProxyType(
                {entry.id: entry for entry in ordered_nodes}
            ),
            nodes_by_kind=MappingProxyType(
                {kind: tuple(bucket) for kind, bucket in nodes_by_kind.items()}
            ),
            edges_by_kind=MappingProxyType(
                {kind: tuple(bucket) for kind, bucket in edges_by_kind.items()}
            ),
            edges_by_endpoint=MappingProxyType(
                {
                    endpoint: frozenset(bucket)
                    for endpoint, bucket in edges_by_endpoint.items()
                }
            ),
            outgoing_by_node=MappingProxyType(
                {
                    endpoint: frozenset(bucket)
                    for endpoint, bucket in outgoing.items()
                }
            ),
            incoming_by_node=MappingProxyType(
                {
                    endpoint: frozenset(bucket)
                    for endpoint, bucket in incoming.items()
                }
            ),
            edges_by_pair=MappingProxyType(
                {pair: tuple(bucket) for pair, bucket in edges_by_pair.items()}
            ),
            node_positions=MappingProxyType(node_positions),
            edge_ids=frozenset(edge_ids),
        )

    def nodes_for_kind(self, kind: ModelKind) -> tuple[NodeEntry, ...]:
        return self.nodes_by_kind.get(kind, ())

    def edges_for_kind(self, kind: ModelKind) -> tuple[EdgeKey, ...]:
        return self.edges_by_kind.get(kind, ())

    def incident(self, node: NodeId) -> frozenset[EdgeKey]:
        return self.edges_by_endpoint.get(node.id, frozenset())

    def outgoing(self, node: NodeId) -> frozenset[EdgeKey]:
        return self.outgoing_by_node.get(node.id, frozenset())

    def incoming(self, node: NodeId) -> frozenset[EdgeKey]:
        return self.incoming_by_node.get(node.id, frozenset())

    def edges_between(
        self,
        source: NodeId,
        target: NodeId,
    ) -> tuple[EdgeKey, ...]:
        return self.edges_by_pair.get((source.id, target.id), ())

    def has_node(self, node: NodeId) -> bool:
        return node.id in self.nodes_by_id

    def has_edge(self, edge: EdgeId) -> bool:
        return edge.id in self.edge_ids

    def neighbors(
        self,
        node: NodeId,
        *,
        direction: Direction = "both",
    ) -> tuple[NodeId, ...]:
        neighbors: set[NodeId] = set()
        if direction in ("out", "both"):
            neighbors.update(edge.target.id for edge in self.outgoing(node))
        if direction in ("in", "both"):
            neighbors.update(edge.source.id for edge in self.incoming(node))
        return tuple(sorted(neighbors))

    def index_of(self, node: NodeId) -> int | None:
        return self.node_positions.get(node.id)

    def shortest_path(
        self,
        source: NodeId,
        target: NodeId,
        *,
        predicate: EdgePredicate | None = None,
    ) -> tuple[EdgeKey, ...] | None:
        start = source.id
        goal = target.id
        if start == goal:
            return ()

        queue: deque[NodeId] = deque([start])
        seen: set[NodeId] = {start}
        predecessor: dict[NodeId, EdgeKey] = {}

        while queue:
            current = queue.popleft()
            for edge in sorted(self.outgoing(current)):
                if predicate is not None and not predicate(edge):
                    continue
                nxt = edge.target.id
                if nxt in seen:
                    continue
                seen.add(nxt)
                predecessor[nxt] = edge
                if nxt == goal:
                    return self._reconstruct(start, goal, predecessor)
                queue.append(nxt)
        return None

    def topological_sort(self) -> tuple[NodeId, ...]:
        indegree = {entry.id: 0 for entry in self.nodes}
        for edge in self.edges:
            indegree[edge.target.id] += 1

        ready = deque(
            node for node in sorted(indegree) if indegree[node] == 0
        )
        ordered: list[NodeId] = []
        while ready:
            current = ready.popleft()
            ordered.append(current)
            for edge in sorted(self.outgoing(current)):
                nxt = edge.target.id
                indegree[nxt] -= 1
                if indegree[nxt] == 0:
                    ready.append(nxt)

        if len(ordered) != len(indegree):
            raise GraphCycleError("Graph contains a cycle")
        return tuple(ordered)

    def _reconstruct(
        self,
        start: NodeId,
        goal: NodeId,
        predecessor: Mapping[NodeId, EdgeKey],
    ) -> tuple[EdgeKey, ...]:
        path: list[EdgeKey] = []
        current = goal
        while current != start:
            edge = predecessor[current]
            path.append(edge)
            current = edge.source.id
        path.reverse()
        return tuple(path)


__all__ = [
    "Direction",
    "EdgePredicate",
    "GraphBackend",
    "GraphCycleError",
    "IndexedBackend",
]
