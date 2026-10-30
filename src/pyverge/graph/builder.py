from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Generic

from pyverge.core.types import ModelKind, VersionValue
from pyverge.graph.graph import MigrationGraph
from pyverge.graph.types import GraphSnapshotSource
from pyverge.registry.errors import CatalogError
from pyverge.versioning import EdgeKey, NodeId


def _freeze(values: Mapping[Any, Any]) -> Mapping[Any, Any]:
    return MappingProxyType(dict(values))


class GraphBuilder(Generic[VersionValue]):
    """Build an immutable migration graph from a snapshot source.

    Executable bindings are deliberately dropped: graph snapshots contain edge
    identity only.  Callables are resolved later through a migration resolver.
    """

    def build(
        self,
        source: GraphSnapshotSource,
    ) -> MigrationGraph[VersionValue]:
        nodes = tuple(source.entries)
        kinds = set(source.entities) | set(source.kinds)
        nodes_by_kind = {kind: tuple(source.kind_entries(kind)) for kind in kinds}
        edges_by_kind: dict[ModelKind, tuple[EdgeKey, ...]] = {}
        edges_by_endpoint: dict[NodeId, set[EdgeKey]] = defaultdict(set)
        executable_edges: set[EdgeKey] = set()
        edge_metadata: dict[EdgeKey, Mapping[str, str]] = {}
        for kind in kinds:
            edges: list[EdgeKey] = []
            for entry in source.edges(kind):
                edge = EdgeKey.from_pair(entry.source, entry.target)
                edges.append(edge)
                edges_by_endpoint[entry.source].add(edge)
                edges_by_endpoint[entry.target].add(edge)
                if entry.is_executable:
                    executable_edges.add(edge)
                    migration = getattr(entry, "migration", None)
                    if migration is not None:
                        edge_metadata[edge] = {
                            "strategy": migration.strategy,
                            "migration_id": migration.identity,
                        }
            edges_by_kind[kind] = tuple(edges)
        namespaces = {node.namespace for node in nodes}
        namespaces.update(
            edge.source.namespace for edges in edges_by_kind.values() for edge in edges
        )
        if len(namespaces) > 1:
            raise CatalogError(
                source.name,
                f"Graph cannot mix namespaces: {sorted(namespaces)}",
            )
        return MigrationGraph(
            name=source.name,
            namespace=source.namespace,
            nodes=nodes,
            nodes_by_kind=_freeze(nodes_by_kind),
            models_by_ref=_freeze(
                {ref: source.get_model_by_ref(ref) for ref in source.models(None)}
            ),
            edges_by_kind=_freeze(edges_by_kind),
            edges_by_endpoint=_freeze(
                {
                    endpoint: frozenset(edges)
                    for endpoint, edges in edges_by_endpoint.items()
                }
            ),
            executable_edges=frozenset(executable_edges),
            edge_metadata=_freeze(edge_metadata),
            content_hashes=_freeze(dict(source.content_hashes)),
        )


__all__ = ["GraphBuilder"]
