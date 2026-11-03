from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pyverge.core.types import ModelKind, VersionValue
from pyverge.core.versioning import EdgeKey, VersionNode

from .model import JgfEdge, JgfNode


@runtime_checkable
class GraphExportSource(Protocol[VersionValue]):
    """Native graph surface needed to project a JGF document."""

    @property
    def namespace(self) -> str: ...

    @property
    def versions(self) -> Sequence[VersionNode[VersionValue]]: ...

    @property
    def kinds(self) -> list[ModelKind]: ...

    def edges(self, kind: ModelKind) -> Sequence[EdgeKey[VersionValue]]: ...


class NodeResolver(Protocol):
    """Map a JGF node back to a concrete version model."""

    def resolve(self, node: JgfNode) -> VersionNode: ...


class EdgeResolver(Protocol):
    """Map a JGF edge back to a graph edge identity."""

    def resolve(self, edge: JgfEdge) -> EdgeKey: ...


__all__ = ["EdgeResolver", "GraphExportSource", "NodeResolver"]
