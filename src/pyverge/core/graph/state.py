from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Generic

from pyverge.core.types import VersionValue
from pyverge.core.versioning import (
    EdgeId,
    EdgeKey,
    ModelRef,
    NodeEntry,
    NodeId,
    VersionNode,
)

from .backend import GraphBackend


@dataclass(frozen=True, slots=True)
class GraphState(Generic[VersionValue]):
    """Frozen inputs and backend-backed indexes for one graph lock.

    The state is backend-neutral. ``MigrationGraph`` is the public read facade;
    backends are implementation detail and never leak their native types.
    """

    name: str
    namespace: str
    nodes: Mapping[NodeId, NodeEntry]
    edges: Mapping[EdgeId, EdgeKey]
    models_by_ref: Mapping[ModelRef, VersionNode[VersionValue]]
    executable_edge_ids: frozenset[EdgeId]
    edge_metadata: Mapping[EdgeId, Mapping[str, str]]
    content_hashes: Mapping[str, EdgeId]
    backend: GraphBackend[VersionValue]

    def edge_key(self, edge: EdgeId) -> EdgeKey:
        return self.edges[edge.id]

    def is_executable(self, edge: EdgeId) -> bool:
        return edge.id in self.executable_edge_ids

    @property
    def executable_edges(self) -> frozenset[EdgeKey]:
        return frozenset(
            self.edges[edge_id] for edge_id in self.executable_edge_ids
        )


__all__ = ["GraphState"]
