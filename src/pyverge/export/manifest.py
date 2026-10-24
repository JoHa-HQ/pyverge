"""Manifest export over a catalog.

CLI consumes this service; it does not assemble JGF manifests itself.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any

from pyverge.jgf import JgfExporter
from pyverge.registry.types import GraphCatalog
from pyverge.versioning import ChangeSet


class ManifestVersion(StrEnum):
    """Supported manifest contract versions."""

    V1 = "1.0"


@dataclass(frozen=True, slots=True)
class ManifestSpec:
    """Required manifest identity and version contract."""

    graph_id: str
    label: str
    manifest_version: ManifestVersion
    tool_version: str


@dataclass(frozen=True, slots=True)
class ManifestExporter:
    """Build a versioned JGF manifest envelope from a catalog."""

    spec: ManifestSpec
    exporter: JgfExporter

    def export(
        self,
        catalog: GraphCatalog,
        *,
        manager: str,
        generated_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Return a JGF envelope with provenance and content hash."""
        document = self.exporter.export_graph(catalog, id=self.spec.graph_id).to_dict()
        graph = document["graph"]
        graph["label"] = self.spec.label
        graph["type"] = "directed"
        graph["metadata"] = {
            "manifest_version": self.spec.manifest_version.value,
            "pyverge_version": self.spec.tool_version,
            "manager": manager,
        }
        content_hash = self.exporter.digest(graph)
        if generated_at is not None:
            graph["metadata"]["generated_at"] = generated_at.isoformat()
        graph["metadata"]["content_hash"] = content_hash
        return document


@dataclass(frozen=True, slots=True)
class ManifestDiff:
    """Semantic difference between two JGF documents.

    Examples:
        >>> left = {"graph": {"nodes": {}, "edges": []}}
        >>> right = {"graph": {"nodes": {"User@1.0.0": {}}, "edges": []}}
        >>> ManifestDiff.compare(left, right).summary()
        ['node added: User@1.0.0']
    """

    nodes: ChangeSet[str] = field(default_factory=ChangeSet)
    edges: ChangeSet[str] = field(default_factory=ChangeSet)
    manifest_version_changed: bool = False

    @property
    def changed(self) -> bool:
        """Whether any semantic content differs."""
        return self.nodes.changed or self.edges.changed or self.manifest_version_changed

    def summary(self) -> list[str]:
        """Human-readable change lines."""
        lines = self.nodes.summary("node") + self.edges.summary("edge")
        if self.manifest_version_changed:
            lines.append("manifest version changed")
        return lines

    @classmethod
    def compare(
        cls,
        left: Mapping[str, Any],
        right: Mapping[str, Any],
    ) -> ManifestDiff:
        """Compare graph content, ignoring generated_at/tool metadata."""
        left_graph = left["graph"]
        right_graph = right["graph"]
        left_nodes = left_graph.get("nodes", {})
        right_nodes = right_graph.get("nodes", {})
        left_edges = {edge["id"]: edge for edge in left_graph.get("edges", [])}
        right_edges = {edge["id"]: edge for edge in right_graph.get("edges", [])}
        left_meta = left_graph.get("metadata", {})
        right_meta = right_graph.get("metadata", {})

        return cls(
            nodes=ChangeSet(
                added=frozenset(right_nodes) - frozenset(left_nodes),
                removed=frozenset(left_nodes) - frozenset(right_nodes),
                modified=frozenset(
                    key
                    for key in left_nodes.keys() & right_nodes.keys()
                    if left_nodes[key] != right_nodes[key]
                ),
            ),
            edges=ChangeSet(
                added=frozenset(right_edges) - frozenset(left_edges),
                removed=frozenset(left_edges) - frozenset(right_edges),
                modified=frozenset(
                    key
                    for key in left_edges.keys() & right_edges.keys()
                    if left_edges[key] != right_edges[key]
                ),
            ),
            manifest_version_changed=left_meta.get("manifest_version")
            != right_meta.get("manifest_version"),
        )


__all__ = ["ManifestDiff", "ManifestExporter", "ManifestSpec", "ManifestVersion"]
