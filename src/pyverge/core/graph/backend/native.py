from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from typing import Any

from pyverge.core.versioning import EdgeId, EdgeKey, NodeId

from .indexed import IndexedBackend
from .port import Direction, EdgePredicate


class NativeBackend:
    """Delegating backend that uses a native graph for traversal.

    Neutral records, digests, and metadata come from an ``IndexedBackend``.
    Subclasses replace adjacency, path, and topological traversal with their
    native graph implementation.
    """

    def __init__(
        self,
        delegate: IndexedBackend,
        native: Any,
        index_by_id: Mapping[NodeId, int],
        id_by_index: tuple[NodeId, ...],
    ) -> None:
        self._delegate = delegate
        self._native = native
        self._index_by_id = index_by_id
        self._id_by_index = id_by_index

    def __getattr__(self, name: str) -> Any:
        return getattr(self._delegate, name)

    def neighbors(
        self,
        node: NodeId,
        *,
        direction: Direction = "both",
    ) -> tuple[NodeId, ...]:
        index = self._index_by_id[node.id]
        selected: set[int] = set()
        if direction in ("out", "both"):
            selected.update(self._out_indices(index))
        if direction in ("in", "both"):
            selected.update(self._in_indices(index))
        return tuple(sorted(self._id_by_index[item] for item in selected))

    def shortest_path(
        self,
        source: NodeId,
        target: NodeId,
        *,
        predicate: EdgePredicate | None = None,
    ) -> tuple[EdgeKey, ...] | None:
        start = self._index_by_id[source.id]
        goal = self._index_by_id[target.id]
        if start == goal:
            return ()

        queue: deque[int] = deque([start])
        seen: set[int] = {start}
        predecessor: dict[int, EdgeKey] = {}

        while queue:
            current = queue.popleft()
            for nxt in sorted(self._out_indices(current)):
                edge = self._edge_to(current, nxt, predicate)
                if edge is None or nxt in seen:
                    continue
                seen.add(nxt)
                predecessor[nxt] = edge
                if nxt == goal:
                    return self._reconstruct(start, goal, predecessor)
                queue.append(nxt)
        return None

    def topological_sort(self) -> tuple[NodeId, ...]:
        return tuple(self._id_by_index[index] for index in self._topological_indices())

    def _edge_to(
        self,
        source: int,
        target: int,
        predicate: EdgePredicate | None,
    ) -> EdgeKey | None:
        for edge in self._delegate.edges_between(
            self._id_by_index[source],
            self._id_by_index[target],
        ):
            if predicate is None or predicate(edge):
                return edge
        return None

    def _reconstruct(
        self,
        start: int,
        goal: int,
        predecessor: dict[int, EdgeKey],
    ) -> tuple[EdgeKey, ...]:
        path: list[EdgeKey] = []
        current = goal
        while current != start:
            edge = predecessor[current]
            path.append(edge)
            current = self._index_by_id[edge.source.id]
        path.reverse()
        return tuple(path)

    def _out_indices(self, index: int) -> list[int]:
        raise NotImplementedError

    def _in_indices(self, index: int) -> list[int]:
        raise NotImplementedError

    def _topological_indices(self) -> list[int]:
        raise NotImplementedError

    def has_edge(self, edge: EdgeId) -> bool:
        return self._delegate.has_edge(edge)


__all__ = ["NativeBackend"]
