from __future__ import annotations

from typing import Any

from pyverge.core.registry.types import ModelCatalog
from pyverge.core.versioning.canonical import ContentHasher

from .model import JgfGraph, JgfNode
from .types import GraphExportSource


class JgfExporter:
    """Project a catalog into JGF with an injected digest strategy."""

    def __init__(self, hasher: ContentHasher) -> None:
        self._hasher = hasher

    @property
    def hasher(self) -> ContentHasher:
        return self._hasher

    def digest(self, value: Any) -> str:
        return self._hasher.digest(value)

    def export_nodes(self, catalog: ModelCatalog) -> tuple[JgfNode, ...]:
        return tuple(
            JgfNode.from_version(node, self._hasher) for node in catalog.versions
        )

    def export_graph(
        self,
        catalog: GraphExportSource,
        *,
        id: str | None = None,
    ) -> JgfGraph:
        edges = [edge for kind in catalog.kinds for edge in catalog.edges(kind)]
        edge_metadata = getattr(catalog, "edge_metadata", None)
        return JgfGraph.from_versions(
            catalog.versions,
            edges,
            hasher=self._hasher,
            id=id or catalog.namespace,
            directed=True,
            edge_metadata=edge_metadata,
        )

    def export_digest(
        self,
        catalog: GraphExportSource,
        *,
        id: str | None = None,
    ) -> str:
        return self._hasher.digest(self.export_graph(catalog, id=id).to_dict())


__all__ = ["JgfExporter"]
