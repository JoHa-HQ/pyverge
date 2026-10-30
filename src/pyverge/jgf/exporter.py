from __future__ import annotations

from typing import Any

from pyverge.graph.types import GraphExportSource
from pyverge.registry.types import ModelCatalog
from pyverge.versioning import JgfGraph, JgfNode
from pyverge.versioning.canonical import ContentHasher


class JgfExporter:
    """Project a catalog into JGF with an injected content-hash strategy."""

    def __init__(self, content_hasher: ContentHasher) -> None:
        self._content_hasher = content_hasher

    @property
    def content_hasher(self) -> ContentHasher:
        return self._content_hasher

    def digest(self, value: Any) -> str:
        return self._content_hasher.digest(value)

    def export_nodes(self, catalog: ModelCatalog) -> tuple[JgfNode, ...]:
        return tuple(node.to_jgf(self._content_hasher) for node in catalog.versions)

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
            hasher=self._content_hasher,
            id=id or catalog.name,
            directed=True,
            edge_metadata=edge_metadata,
        )

    def content_hash(
        self,
        catalog: GraphExportSource,
        *,
        id: str | None = None,
    ) -> str:
        return self._content_hasher.digest(self.export_graph(catalog, id=id).to_dict())


__all__ = ["JgfExporter"]
