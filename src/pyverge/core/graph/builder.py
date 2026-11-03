from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any, Generic

from pyverge.core.graph.backend import IndexedBackend
from pyverge.core.graph.graph import MigrationGraph
from pyverge.core.graph.state import GraphState
from pyverge.core.graph.types import GraphSnapshotSource
from pyverge.core.registry.errors import CatalogError
from pyverge.core.types import VersionValue
from pyverge.core.versioning import EdgeId, EdgeKey


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
        nodes = tuple(sorted(source.entries))
        kinds = set(source.entities) | set(source.kinds)
        edges_by_id: dict[EdgeId, EdgeKey] = {}
        executable_edge_ids: set[EdgeId] = set()
        edge_metadata: dict[EdgeId, Mapping[str, str]] = {}
        for kind in kinds:
            for entry in source.edges(kind):
                edge = EdgeKey.from_pair(
                    entry.source,
                    entry.target,
                    discriminator=getattr(entry, "discriminator", "default"),
                    ref=entry.ref,
                )
                edges_by_id[edge.id] = edge
                if entry.is_executable:
                    executable_edge_ids.add(edge.id)
                    migration = getattr(entry, "migration", None)
                    if migration is not None:
                        edge_metadata[edge.id] = {
                            "strategy": migration.strategy,
                            "migration_id": migration.identity,
                        }

        edges = tuple(sorted(edges_by_id.values()))
        namespaces = {node.namespace for node in nodes}
        namespaces.update(edge.namespace for edge in edges)
        if len(namespaces) > 1:
            raise CatalogError(
                source.namespace,
                f"Graph cannot mix namespaces: {sorted(namespaces)}",
            )

        backend = IndexedBackend[VersionValue].build(nodes, edges)
        state = GraphState(
            name=source.namespace,
            namespace=source.namespace,
            nodes=_freeze({entry.id: entry for entry in nodes}),
            edges=_freeze(dict(edges_by_id)),
            models_by_ref=_freeze(
                {ref: source.get_model_by_ref(ref) for ref in source.models(None)}
            ),
            executable_edge_ids=frozenset(executable_edge_ids),
            edge_metadata=_freeze(
                {
                    edge_id: MappingProxyType(dict(metadata))
                    for edge_id, metadata in edge_metadata.items()
                }
            ),
            content_hashes=_freeze(
                {
                    digest: edge.id
                    for digest, edge in source.content_hashes.items()
                }
            ),
            backend=backend,
        )
        return MigrationGraph(state=state)


__all__ = ["GraphBuilder"]
