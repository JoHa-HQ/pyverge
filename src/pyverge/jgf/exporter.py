from __future__ import annotations

from typing import Any, cast

from pyverge.registry.types import GraphCatalog, ModelCatalog
from pyverge.versioning import JgfGraph, JgfNode
from pyverge.versioning.canonical import ContentHasher


class JgfExporter:
    """Project a catalog into JGF with an injected content-hash strategy."""

    def __init__(self, content_hasher: ContentHasher) -> None:
        self._content_hasher = content_hasher

    @property
    def content_hasher(self) -> ContentHasher:
        """The configured content-hash strategy."""
        return self._content_hasher

    def digest(self, value: Any) -> str:
        """Hash a JGF document/value with the configured strategy."""
        return self._content_hasher.digest(value)

    def export_nodes(self, catalog: ModelCatalog) -> tuple[JgfNode, ...]:
        """Export model nodes in catalog order."""
        return tuple(node.to_jgf(self._content_hasher) for node in catalog.versions)

    def export_graph(
        self,
        catalog: GraphCatalog,
        *,
        id: str | None = None,
    ) -> JgfGraph:
        """Export the full JGF graph from a graph catalog."""
        edges = cast(
            Any,
            [edge for kind in catalog.kinds for edge in catalog.migrations(kind)],
        )
        return JgfGraph.from_versions(
            catalog.versions,
            edges,
            hasher=self._content_hasher,
            id=id or catalog.name,
            directed=True,
        )

    def content_hash(
        self,
        catalog: GraphCatalog,
        *,
        id: str | None = None,
    ) -> str:
        """Canonical content hash of the exported graph."""
        return self._content_hasher.digest(self.export_graph(catalog, id=id).to_dict())


__all__ = ["JgfExporter"]
