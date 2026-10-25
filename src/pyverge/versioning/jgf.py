from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .canonical import ContentHasher
from .primitives import VersionEdge, VersionNode


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
        return cls(
            id=node.jgf_id,
            label=node.jgf_id,
            metadata={
                "kind": node.kind,
                "version": str(node.version[1]),
                "model": node.model_id,
                "fields": sorted(node.fields),
                "references": sorted(
                    f"{kind}@{version}" for kind, version in node.references
                ),
                "schema_hash": node.content_hash(hasher),
            },
        )

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
    def from_version_edge(cls, edge: VersionEdge[Any]) -> JgfEdge:
        return cls(
            id=edge.jgf_id,
            source=edge.source.jgf_id,
            target=edge.target.jgf_id,
            metadata={
                "kind": edge.kind,
                "source_version": str(edge.source.version[1]),
                "target_version": str(edge.target.version[1]),
                "strategy": edge.migration.strategy,
                "migration_id": edge.migration.identity,
            },
        )

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
        edges: Iterable[VersionEdge[Any]] = (),
        *,
        hasher: ContentHasher,
        id: str,
        directed: bool,
        metadata: Mapping[str, Any] | None = None,
    ) -> JgfGraph:
        return cls(
            id=id,
            directed=directed,
            nodes=tuple(node.to_jgf(hasher) for node in versions),
            edges=tuple(edge.to_jgf() for edge in edges),
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
