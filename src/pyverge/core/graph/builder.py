from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any, Generic

from pyverge.core.graph.backend import GraphBackend, IndexedBackend
from pyverge.core.graph.errors import RevisionMismatchError
from pyverge.core.graph.graph import MigrationGraph
from pyverge.core.graph.revision import (
    Revision,
    VersionVectorRevisionPolicy,
    manifest_digest,
    version_strategy,
)
from pyverge.core.graph.types import GraphSnapshotSource
from pyverge.core.registry.errors import CatalogError
from pyverge.core.types import VersionValue
from pyverge.core.versioning import EdgeId, EdgeKey, HookRef


def _freeze(values: Mapping[Any, Any]) -> Mapping[Any, Any]:
    return MappingProxyType(dict(values))


class GraphBuilder(Generic[VersionValue]):
    """Build an immutable migration graph from a snapshot source.

    Executable bindings are deliberately dropped: graph snapshots contain edge
    identity only.  Callables are resolved later through a migration resolver.
    """

    def __init__(
        self,
        backend_factory: Callable[..., GraphBackend[VersionValue]] | None = None,
    ) -> None:
        self._backend_factory = backend_factory

    def build(
        self,
        source: GraphSnapshotSource,
        *,
        revision: Revision | None = None,
    ) -> MigrationGraph[VersionValue]:
        hasher = source.hasher
        entries = tuple(source.entries)
        version_strategy(entry.version for entry in entries)
        nodes = tuple(sorted(entries))
        node_digests = {node.id: node.digest(hasher) for node in nodes}
        kinds = set(source.entities) | set(source.kinds)
        edges_by_id: dict[EdgeId, EdgeKey] = {}
        edge_digests: dict[EdgeId, str] = {}
        hook_specs: dict[EdgeId, tuple[HookRef, ...]] = {}
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
                edge_digests[edge.id] = entry.digest(hasher)
                hooks = source.get_hooks(edge)
                if hooks:
                    hook_specs[edge.id] = tuple(
                        sorted(hooks, key=lambda ref: ref.digest(hasher))
                    )
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

        factory = self._backend_factory or IndexedBackend[VersionValue].build
        backend = factory(
            nodes,
            edges,
            name=source.namespace,
            namespace=source.namespace,
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
            digests=_freeze(
                {digest: edge.id for digest, edge in source.digests.items()}
            ),
            node_digests=_freeze(node_digests),
            edge_digests=_freeze(edge_digests),
            hook_specs=_freeze(hook_specs),
        )
        derived = VersionVectorRevisionPolicy[VersionValue]().derive(
            backend,
            hasher=hasher,
        )
        if revision is not None and revision != derived:
            raise RevisionMismatchError(expected=revision, actual=derived)
        return MigrationGraph(
            backend=backend,
            revision=derived,
            _manifest_digest=manifest_digest(
                backend,
                derived,
                hasher=hasher,
            ),
        )


__all__ = ["GraphBuilder"]
