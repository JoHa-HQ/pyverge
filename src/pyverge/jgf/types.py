from __future__ import annotations

from typing import Protocol

from pyverge.versioning import EdgeKey, JgfEdge, JgfNode, VersionNode


class NodeResolver(Protocol):
    """Map a JGF node back to a concrete version model."""

    def resolve(self, node: JgfNode) -> VersionNode: ...


class EdgeResolver(Protocol):
    """Map a JGF edge back to a graph edge identity."""

    def resolve(self, edge: JgfEdge) -> EdgeKey: ...


__all__ = ["EdgeResolver", "NodeResolver"]
