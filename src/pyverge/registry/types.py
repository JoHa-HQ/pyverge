"""Registry ports: read models, write capabilities, and the aggregate."""

from __future__ import annotations

from typing import Any, Protocol

from pyverge.core.types import (
    Attachable,
    ModelHandle,
    ModelKind,
    ModelVersionKey,
    VersionValue,
)
from pyverge.versioning import (
    EdgeKey,
    Migratable,
    Transitional,
    Versionable,
    VersionEdge,
    VersionNode,
)


class ModelCatalog(Protocol[VersionValue]):
    """Read-only model surface used by discovery and planning."""

    @property
    def name(self) -> str: ...
    @property
    def versions(self) -> list[VersionNode[VersionValue]]: ...
    @property
    def kinds(self) -> list[ModelKind]: ...
    @property
    def entities(self) -> list[ModelKind]: ...
    def models(self, kind: ModelKind | None) -> frozenset[ModelHandle]: ...
    def kind_versions(self, kind: ModelKind) -> list[VersionNode[VersionValue]]: ...
    def has_model(self, key: Any) -> bool: ...
    def find_model(self, key: Any) -> VersionNode[VersionValue] | None: ...
    def get_model(self, key: Any) -> VersionNode[VersionValue]: ...
    def get_model_by_handle(self, handle: ModelHandle) -> VersionNode[VersionValue]: ...
    def latest(self, kind: ModelKind) -> VersionNode[VersionValue]: ...
    def earliest(self, kind: ModelKind) -> VersionNode[VersionValue]: ...
    @property
    def latest_version(self) -> VersionNode[VersionValue]: ...
    def missing_references(
        self, node: Versionable[VersionValue]
    ) -> frozenset[ModelVersionKey]: ...


class PathCatalog(Protocol[VersionValue]):
    """Narrow read port needed to resolve migration paths."""

    def migration_path(
        self,
        from_version: Versionable[VersionValue],
        to_version: Versionable[VersionValue],
    ) -> list[tuple[VersionNode[VersionValue], VersionNode[VersionValue]]]: ...


class ContentHashLookup(Protocol):
    """Optional content-address index for manifest/debug queries."""

    def find_edge_by_content_hash(self, value: str) -> EdgeKey | None: ...


class GraphCatalog(
    PathCatalog[VersionValue], ModelCatalog[VersionValue], Protocol[VersionValue]
):
    """Read-only migration graph surface used by runtime planning."""

    def migrations(self, kind: ModelKind) -> list[Migratable[VersionValue]]: ...
    def migrations_of(self, key: Any) -> frozenset[Migratable[VersionValue]]: ...
    def has_migration(self, key: Transitional) -> bool: ...
    def get_migration(self, key: Transitional) -> Migratable[VersionValue]: ...
    def get_migration_by_edge(self, key: Transitional) -> Migratable[VersionValue]: ...
    def is_adjacent(self, key: Transitional) -> bool: ...
    def is_critical_edge(self, key: Transitional) -> bool: ...
    def has_hooks(self, key: Transitional) -> bool: ...
    def hooks(self, key: Transitional | None = None) -> list[Attachable]: ...
    def get_hooks(self, key: Transitional) -> list[Attachable]: ...
    def snapshot(self) -> GraphCatalog[VersionValue]: ...


class ModelWrite(Protocol[VersionValue]):
    """Write-side model capability."""

    def store_model(
        self, version: VersionNode[VersionValue]
    ) -> VersionNode[VersionValue]: ...
    def reconcile_model(
        self, version: VersionNode[VersionValue]
    ) -> VersionNode[VersionValue]: ...
    def remove_model(self, key: Any) -> None: ...
    def remove_model_by_handle(self, handle: ModelHandle) -> None: ...
    def clear_models(self) -> None: ...


class MigrationWrite(Protocol[VersionValue]):
    """Write-side migration capability."""

    def store_migration(self, key: VersionEdge[VersionValue]) -> Any: ...
    def remove_migration(self, key: Transitional) -> None: ...
    def remove_migration_range(
        self,
        from_version: Versionable[VersionValue],
        to_version: Versionable[VersionValue],
    ) -> None: ...
    def clear_migrations(self) -> None: ...
    def add_hook(self, key: Transitional, hook: Attachable) -> None: ...
    def remove_hook(
        self, key: Transitional, hook: Attachable | None = None
    ) -> None: ...
    def clear_hooks(self, key: Transitional | None = None) -> None: ...


class RegistryPort(
    GraphCatalog[VersionValue],
    ModelWrite[VersionValue],
    MigrationWrite[VersionValue],
    Protocol[VersionValue],
):
    """Full catalog contract for an in-memory or remote adapter."""


__all__ = [
    "ContentHashLookup",
    "GraphCatalog",
    "MigrationWrite",
    "ModelCatalog",
    "ModelWrite",
    "PathCatalog",
    "RegistryPort",
]
