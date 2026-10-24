"""JGF import service: parse a document and register through registry write ports."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pyverge.registry.types import MigrationWrite, ModelWrite
from pyverge.versioning import JgfGraph

from .types import EdgeResolver, NodeResolver


class JgfImporter:
    """Import a JGF document into a registry using explicit resolvers."""

    def __init__(self, node_resolver: NodeResolver) -> None:
        self._node_resolver = node_resolver

    def import_graph(
        self,
        document: Mapping[str, Any],
        *,
        models: ModelWrite,
        migrations: MigrationWrite | None = None,
        edge_resolver: EdgeResolver | None = None,
    ) -> JgfGraph:
        """Register nodes (and edges when a resolver is supplied)."""
        graph = JgfGraph.from_dict(document)
        for node in graph.nodes:
            models.store_model(self._node_resolver.resolve(node))
        if graph.edges:
            if migrations is None or edge_resolver is None:
                raise ValueError(
                    "Importing JGF edges requires both a migration write port "
                    "and an EdgeResolver"
                )
            for edge in graph.edges:
                migrations.store_migration(edge_resolver.resolve(edge))
        return graph


__all__ = ["JgfImporter"]
