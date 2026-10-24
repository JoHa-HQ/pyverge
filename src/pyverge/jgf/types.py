"""Export-domain protocols for JGF import resolution."""

from __future__ import annotations

from typing import Protocol

from pyverge.versioning import JgfEdge, JgfNode, VersionEdge, VersionNode


class NodeResolver(Protocol):
    """Map a JGF node back to a concrete version model."""

    def resolve(self, node: JgfNode) -> VersionNode: ...


class EdgeResolver(Protocol):
    """Map a JGF edge back to a concrete migration edge."""

    def resolve(self, edge: JgfEdge) -> VersionEdge: ...


__all__ = ["EdgeResolver", "NodeResolver"]
