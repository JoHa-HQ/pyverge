from __future__ import annotations

from collections.abc import Iterable, Mapping
from importlib import import_module
from typing import Any

from pyverge.core.types import VersionValue
from pyverge.core.versioning import (
    EdgeId,
    EdgeKey,
    HookRef,
    ModelRef,
    NodeEntry,
    NodeId,
    VersionNode,
)

from .indexed import IndexedBackend
from .native import NativeBackend
from .port import BackendUnavailableError


def _igraph() -> Any:
    try:
        return import_module("igraph")
    except ImportError as error:
        raise BackendUnavailableError("igraph is required for IgraphBackend") from error


class IgraphBackend(NativeBackend):
    """Optional igraph-backed traversal over the indexed graph."""

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
    ) -> IgraphBackend:
        ig = _igraph()
        delegate = IndexedBackend.build(
            nodes,
            edges,
            name=name,
            namespace=namespace,
            models_by_ref=models_by_ref,
            executable_edge_ids=executable_edge_ids,
            edge_metadata=edge_metadata,
            digests=digests,
            node_digests=node_digests,
            edge_digests=edge_digests,
            hook_specs=hook_specs,
        )
        index_by_id = {node.id: index for index, node in enumerate(delegate.nodes)}
        native = ig.Graph(directed=True)
        native.add_vertices(len(delegate.nodes))
        native.add_edges(
            [
                (
                    index_by_id[edge.source.id],
                    index_by_id[edge.target.id],
                )
                for edge in delegate.edges
            ]
        )
        return cls(
            delegate=delegate,
            native=native,
            index_by_id=index_by_id,
            id_by_index=tuple(node.id for node in delegate.nodes),
        )

    def _out_indices(self, index: int) -> list[int]:
        return list(self._native.neighbors(index, mode="out"))

    def _in_indices(self, index: int) -> list[int]:
        return list(self._native.neighbors(index, mode="in"))

    def _topological_indices(self) -> list[int]:
        return list(self._native.topological_sorting(mode="out"))


__all__ = ["IgraphBackend"]
