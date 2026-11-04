from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Generic, cast

from pyverge.core.types import ModelKind, VersionValue
from pyverge.core.versioning import (
    EdgeId,
    EdgeKey,
    HookRef,
    ModelRef,
    NodeEntry,
    NodeId,
    VersionNode,
)

from .port import Direction, EdgePredicate, GraphCycleError


@dataclass(frozen=True, slots=True)
class IndexedBackend(Generic[VersionValue]):
    """Dependency-free backend using frozen maps and sorted tuples.

    The backend owns its state and every index derived from it.
    """

    name: str
    namespace: str
    nodes: tuple[NodeEntry, ...]
    edges: tuple[EdgeKey, ...]
    nodes_by_id: Mapping[NodeId, NodeEntry]
    edges_by_id: Mapping[EdgeId, EdgeKey]
    nodes_by_kind: Mapping[ModelKind, tuple[NodeEntry, ...]]
    edges_by_kind: Mapping[ModelKind, tuple[EdgeKey, ...]]
    edges_by_endpoint: Mapping[NodeId, frozenset[EdgeKey]]
    outgoing_by_node: Mapping[NodeId, frozenset[EdgeKey]]
    incoming_by_node: Mapping[NodeId, frozenset[EdgeKey]]
    edges_by_pair: Mapping[tuple[NodeId, NodeId], tuple[EdgeKey, ...]]
    node_positions: Mapping[NodeId, int]
    edge_ids: frozenset[EdgeId]
    models_by_ref: Mapping[ModelRef, VersionNode[VersionValue]]
    executable_edge_ids: frozenset[EdgeId]
    edge_metadata: Mapping[EdgeId, Mapping[str, str]]
    digests: Mapping[str, EdgeId]
    node_digests: Mapping[NodeId, str]
    edge_digests: Mapping[EdgeId, str]
    hook_specs: Mapping[EdgeId, tuple[HookRef, ...]]

    @classmethod
    def build(  # noqa: PLR0913
        cls,
        nodes: Iterable[NodeEntry],
        edges: Iterable[EdgeKey],
        *,
        name: str = "",
        namespace: str = "",
        models_by_ref: Mapping[ModelRef, VersionNode[VersionValue]] | None = None,
        executable_edge_ids: Iterable[EdgeId] = (),
        edge_metadata: Mapping[EdgeId, Mapping[str, str]] | None = None,
        digests: Mapping[str, EdgeId] | None = None,
        node_digests: Mapping[NodeId, str] | None = None,
        edge_digests: Mapping[EdgeId, str] | None = None,
        hook_specs: Mapping[EdgeId, tuple[HookRef, ...]] | None = None,
    ) -> IndexedBackend[VersionValue]:
        ordered_nodes = tuple(sorted(nodes))
        ordered_edges = tuple(sorted(edges))
        resolved_namespace = namespace or (
            ordered_nodes[0].namespace
            if ordered_nodes
            else (ordered_edges[0].namespace if ordered_edges else "")
        )
        resolved_models: dict[ModelRef, VersionNode[VersionValue]] = (
            dict(models_by_ref) if models_by_ref is not None else {}
        )
        if models_by_ref is None:
            for node in ordered_nodes:
                if node.is_model:
                    resolved_models[cast("ModelRef", node.modelref)] = cast(
                        "VersionNode[VersionValue]", node
                    )

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
            name=name or resolved_namespace,
            namespace=resolved_namespace,
            nodes=ordered_nodes,
            edges=ordered_edges,
            nodes_by_id=MappingProxyType({entry.id: entry for entry in ordered_nodes}),
            edges_by_id=MappingProxyType({edge.id: edge for edge in ordered_edges}),
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
                {endpoint: frozenset(bucket) for endpoint, bucket in outgoing.items()}
            ),
            incoming_by_node=MappingProxyType(
                {endpoint: frozenset(bucket) for endpoint, bucket in incoming.items()}
            ),
            edges_by_pair=MappingProxyType(
                {pair: tuple(bucket) for pair, bucket in edges_by_pair.items()}
            ),
            node_positions=MappingProxyType(node_positions),
            edge_ids=frozenset(edge_ids),
            models_by_ref=MappingProxyType(resolved_models),
            executable_edge_ids=frozenset(executable_edge_ids),
            edge_metadata=MappingProxyType(dict(edge_metadata or {})),
            digests=MappingProxyType(dict(digests or {})),
            node_digests=MappingProxyType(dict(node_digests or {})),
            edge_digests=MappingProxyType(dict(edge_digests or {})),
            hook_specs=MappingProxyType(dict(sorted((hook_specs or {}).items()))),
        )

    @property
    def executable_edges(self) -> frozenset[EdgeKey]:
        return frozenset(
            self.edges_by_id[edge_id] for edge_id in self.executable_edge_ids
        )

    def edge_key(self, edge: EdgeId) -> EdgeKey:
        return self.edges_by_id[edge.id]

    def is_executable(self, edge: EdgeId) -> bool:
        return edge.id in self.executable_edge_ids

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

        ready = deque(node for node in sorted(indegree) if indegree[node] == 0)
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


__all__ = ["IndexedBackend"]
