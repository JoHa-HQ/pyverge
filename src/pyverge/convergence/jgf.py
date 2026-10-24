"""JGF import service: parse a document and register through catalog ports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from pyverge.versioning import JgfEdge, JgfGraph, JgfNode, VersionEdge, VersionNode

from .catalog.ports import (
    MigrationRegistrar,
    ModelRegistrar,
)


class NodeResolver(Protocol):
    """Map a JGF node back to a concrete version model."""

    def resolve(self, node: JgfNode) -> VersionNode: ...


class EdgeResolver(Protocol):
    """Map a JGF edge back to a concrete migration edge."""

    def resolve(self, edge: JgfEdge) -> VersionEdge: ...


class JgfImporter:
    """Import a JGF document into a catalog using explicit resolvers."""

    def __init__(self, node_resolver: NodeResolver) -> None:
        self._node_resolver = node_resolver

    def import_graph(
        self,
        document: Mapping[str, Any],
        *,
        models: ModelRegistrar,
        migrations: MigrationRegistrar | None = None,
        edge_resolver: EdgeResolver | None = None,
    ) -> JgfGraph:
        """Register nodes (and edges when a resolver is supplied)."""
        graph = JgfGraph.from_dict(document)
        for node in graph.nodes:
            models.store_model(self._node_resolver.resolve(node))
        if graph.edges:
            if migrations is None or edge_resolver is None:
                raise ValueError(
                    "Importing JGF edges requires both a migration registrar "
                    "and an EdgeResolver"
                )
            for edge in graph.edges:
                migrations.store_migration(edge_resolver.resolve(edge))
        return graph


__all__ = ["EdgeResolver", "JgfImporter", "NodeResolver"]
