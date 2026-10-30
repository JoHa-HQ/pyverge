from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .canonical import Addressable, ContentHasher
from .graph import VersionEdge, VersionNode
from .identity import EdgeKey, VersionKey
from .schema import ModelDescriptor


@dataclass(frozen=True, slots=True)
class JgfNode:
    """A JGF node projected from a materialized version."""

    id: str
    label: str
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, node_id: str, value: Mapping[str, Any]) -> JgfNode:
        return cls(
            id=node_id,
            label=value.get("label", node_id),
            metadata=dict(value.get("metadata", {})),
        )

    @classmethod
    def from_version(cls, node: VersionNode[Any], hasher: ContentHasher) -> JgfNode:
        return cls.from_descriptor(node, node.descriptor, hasher)

    @classmethod
    def from_descriptor(
        cls,
        key: VersionKey[Any],
        descriptor: ModelDescriptor,
        hasher: ContentHasher,
    ) -> JgfNode:
        references = sorted(str(reference) for reference in descriptor.references)
        content = {
            "id": str(key),
            "model": descriptor.ref.model_id,
            "fields": sorted(descriptor.fields),
            "references": references,
        }
        rendered = str(key)
        return cls(
            id=rendered,
            label=rendered,
            metadata={
                **({"namespace": key.namespace} if key.namespace else {}),
                "kind": key.kind,
                "version": str(key.version),
                "model": descriptor.ref.model_id,
                "fields": sorted(descriptor.fields),
                "references": references,
                "schema_hash": hasher.digest(content),
            },
        )

    @classmethod
    def from_addressable(cls, value: Addressable, hasher: ContentHasher) -> JgfNode:
        payload = value.to_canonical()
        metadata = (
            dict(payload) if isinstance(payload, Mapping) else {"canonical": payload}
        )
        metadata["content_hash"] = value.content_hash(hasher)
        rendered = str(value)
        return cls(id=rendered, label=rendered, metadata=metadata)

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class JgfEdge:
    """A JGF edge projected from a migration edge."""

    id: str
    source: str
    target: str
    directed: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> JgfEdge:
        return cls(
            id=value["id"],
            source=value["source"],
            target=value["target"],
            directed=bool(value.get("directed", True)),
            metadata=dict(value.get("metadata", {})),
        )

    @classmethod
    def from_edge_key(
        cls,
        edge: EdgeKey[Any],
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> JgfEdge:
        source = str(edge.source)
        target = str(edge.target)
        projected: dict[str, Any] = {
            **({"namespace": edge.namespace} if edge.namespace else {}),
            "kind": edge.kind,
            "source_version": str(edge.source.version),
            "target_version": str(edge.target.version),
        }
        migration = getattr(edge, "migration", None)
        if migration is not None:
            projected["strategy"] = migration.strategy
            projected["migration_id"] = migration.identity
        if metadata:
            projected.update(metadata)
        return cls(
            id=f"{source}->{target}",
            source=source,
            target=target,
            metadata=projected,
        )

    @classmethod
    def from_version_edge(cls, edge: VersionEdge[Any]) -> JgfEdge:
        return cls.from_edge_key(edge)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "directed": self.directed,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class JgfGraph:
    """A JGF v2 graph envelope."""

    id: str
    directed: bool
    nodes: tuple[JgfNode, ...] = ()
    edges: tuple[JgfEdge, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, document: Mapping[str, Any]) -> JgfGraph:
        graph = document["graph"]
        nodes = [
            JgfNode.from_dict(node_id, node)
            for node_id, node in graph.get("nodes", {}).items()
        ]
        edges = [JgfEdge.from_dict(edge) for edge in graph.get("edges", [])]
        return cls(
            id=graph["id"],
            directed=bool(graph["directed"]),
            nodes=tuple(nodes),
            edges=tuple(edges),
            metadata=dict(graph.get("metadata", {})),
        )

    @classmethod
    def from_versions(  # noqa: PLR0913
        cls,
        versions: Iterable[VersionNode[Any]],
        edges: Iterable[EdgeKey[Any]] = (),
        *,
        hasher: ContentHasher,
        id: str,
        directed: bool,
        metadata: Mapping[str, Any] | None = None,
        edge_metadata: Mapping[EdgeKey[Any], Mapping[str, Any]] | None = None,
    ) -> JgfGraph:
        projected_metadata = edge_metadata or {}
        return cls(
            id=id,
            directed=directed,
            nodes=tuple(node.to_jgf(hasher) for node in versions),
            edges=tuple(
                JgfEdge.from_edge_key(edge, metadata=projected_metadata.get(edge))
                for edge in edges
            ),
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict[str, Any]:
        graph: dict[str, Any] = {
            "id": self.id,
            "directed": self.directed,
            "nodes": {node.id: node.to_dict() for node in self.nodes},
            "edges": [edge.to_dict() for edge in self.edges],
        }
        if self.metadata:
            graph["metadata"] = dict(self.metadata)
        return {"graph": graph}


__all__ = [
    "JgfEdge",
    "JgfGraph",
    "JgfNode",
]
