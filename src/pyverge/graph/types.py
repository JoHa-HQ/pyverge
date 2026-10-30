from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol, runtime_checkable

from pyverge.core.types import Attachable, MigrationFunc, ModelKind, VersionValue
from pyverge.registry.types import ModelCatalog, PathCatalog
from pyverge.versioning import (
    Diffable,
    EdgeEntry,
    EdgeKey,
    ModelRef,
    NodeEntry,
    Transitional,
    VersionNode,
)


@runtime_checkable
class GraphView(ModelCatalog[VersionValue], Protocol[VersionValue]):
    """Broad read-only graph surface consumed by graph planning."""

    def has_migration(self, key: Transitional[VersionValue]) -> bool: ...


class PathGraphView(
    GraphView[VersionValue], PathCatalog[VersionValue], Protocol[VersionValue]
):
    """Graph view with migration-path resolution."""


@runtime_checkable
class GraphExportSource(Protocol[VersionValue]):
    """Native graph surface needed to project a JGF document."""

    @property
    def name(self) -> str: ...

    @property
    def versions(self) -> Sequence[VersionNode[VersionValue]]: ...

    @property
    def kinds(self) -> list[ModelKind]: ...

    def edges(self, kind: ModelKind) -> Sequence[EdgeKey[VersionValue]]: ...


@runtime_checkable
class MigrationDefinition(Protocol[VersionValue]):
    """Executable binding attached to one graph edge identity."""

    @property
    def source(self) -> VersionNode[VersionValue]: ...

    @property
    def target(self) -> VersionNode[VersionValue]: ...

    @property
    def diff(self) -> Diffable[VersionValue]: ...

    @property
    def func(self) -> MigrationFunc: ...


@runtime_checkable
class MigrationResolver(Protocol[VersionValue]):
    """Resolve executable migration bindings and hooks by edge identity."""

    def resolve(
        self, key: EdgeKey[VersionValue]
    ) -> MigrationDefinition[VersionValue]: ...

    def hooks(self, key: EdgeKey[VersionValue]) -> Sequence[Attachable]: ...


@runtime_checkable
class GraphSnapshotSource(Protocol):
    """Read-only source used to compile an immutable migration graph."""

    @property
    def name(self) -> str: ...

    @property
    def namespace(self) -> str: ...

    @property
    def entries(self) -> Sequence[NodeEntry]: ...

    @property
    def content_hashes(self) -> Mapping[str, EdgeKey]: ...

    @property
    def entities(self) -> list[ModelKind]: ...

    @property
    def kinds(self) -> list[ModelKind]: ...

    def kind_entries(self, kind: ModelKind) -> list[NodeEntry]: ...

    def edges(self, kind: ModelKind) -> list[EdgeEntry]: ...

    def models(self, kind: ModelKind | None) -> frozenset[ModelRef]: ...

    def get_model_by_ref(self, ref: ModelRef) -> VersionNode: ...


__all__ = [
    "GraphExportSource",
    "GraphSnapshotSource",
    "GraphView",
    "MigrationDefinition",
    "MigrationResolver",
    "PathGraphView",
]
