from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal, Protocol, runtime_checkable

from pyverge.core.types import (
    ModelKind,
    VersionValue,
    VersionValue_co,
)
from pyverge.core.versioning import (
    Comparable,
    Diff,
    Diffable,
    EdgeEntry,
    EdgeKey,
    HookRef,
    Identifiable,
    Migratable,
    ModelRef,
    NodeEntry,
    Transitional,
    Versionable,
    VersionKey,
    VersionNode,
)

if TYPE_CHECKING:
    from pyverge.core.types import MigrationFunc
    from pyverge.migrations.json_patch import JsonPatch
    from pyverge.migrations.spec import MigrationSpec


HealthSeverity = Literal["info", "warning", "error"]
"""Severity carried by a :class:`HealthIssue`."""

HealthFailLevel = Literal["info", "warning", "error", "never"]
"""Threshold at which a health check raises.

Ordering is ``info`` < ``warning`` < ``error``. An issue blocks when its
severity is at or above the configured level. ``"never"`` disables the check.
"""

HEALTH_SEVERITY_ORDER: tuple[HealthSeverity, ...] = ("info", "warning", "error")
"""Severity ordering, lowest first."""


@dataclass(frozen=True, slots=True)
class HealthIssue:
    """One health finding for a node or edge."""

    code: str
    severity: HealthSeverity
    entity: VersionKey | EdgeKey
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def blocks(self, fail_level: HealthFailLevel) -> bool:
        """Return whether this issue meets or exceeds *fail_level*.

        Args:
            fail_level: Threshold to compare against. ``"never"`` never blocks.

        Returns:
            bool: ``True`` when this issue is at or above the threshold.
        """
        if fail_level == "never":
            return False
        return HEALTH_SEVERITY_ORDER.index(self.severity) >= (
            HEALTH_SEVERITY_ORDER.index(fail_level)
        )

    @property
    def is_node(self) -> bool:
        return isinstance(self.entity, VersionKey)

    @property
    def is_edge(self) -> bool:
        return isinstance(self.entity, EdgeKey)


@runtime_checkable
class ReflectionPort(Protocol[VersionValue]):
    """Diff-based reflection for model and migration artifacts."""

    def diff(
        self,
        source: Versionable[VersionValue],
        target: Comparable[VersionValue],
        *,
        migration: JsonPatch | MigrationFunc | None = None,
    ) -> Diff[VersionValue]: ...

    def reflect(self, diff: Diffable) -> VersionNode[VersionValue]: ...

    def bind(self, diff: Diffable) -> Any: ...


class ModelCatalog(Protocol[VersionValue]):
    """Read-only model surface used by discovery and planning."""

    @property
    def namespace(self) -> str: ...
    @property
    def versions(self) -> list[VersionNode[VersionValue]]: ...
    @property
    def kinds(self) -> list[ModelKind]: ...
    @property
    def entities(self) -> list[ModelKind]: ...
    def models(self, kind: ModelKind | None) -> frozenset[ModelRef]: ...
    def kind_versions(self, kind: ModelKind) -> list[VersionNode[VersionValue]]: ...
    def has_model(self, key: Any) -> bool: ...
    def has_entry(self, key: Any) -> bool: ...
    def find_model(self, key: Any) -> VersionNode[VersionValue] | None: ...
    def get_model(self, key: Any) -> VersionNode[VersionValue]: ...
    def get_model_by_ref(self, ref: ModelRef) -> VersionNode[VersionValue]: ...
    def latest(self, kind: ModelKind) -> VersionNode[VersionValue]: ...
    def earliest(self, kind: ModelKind) -> VersionNode[VersionValue]: ...
    @property
    def latest_version(self) -> VersionNode[VersionValue]: ...


class PathCatalog(Protocol[VersionValue]):
    """Narrow read port needed to resolve migration paths."""

    def edge_path(
        self,
        from_version: VersionNode[VersionValue],
        to_version: VersionNode[VersionValue],
    ) -> list[EdgeKey[VersionValue]]: ...


class DigestLookup(Protocol):
    """Optional digest index for manifest/debug queries."""

    def find_edge_by_digest(self, value: str) -> EdgeKey | None: ...


class GraphCatalog(ModelCatalog[VersionValue], Protocol[VersionValue]):
    """Read-only migration graph surface used by runtime planning."""

    def migrations(self, kind: ModelKind) -> list[Migratable[VersionValue]]: ...
    def edges(self, kind: ModelKind) -> list[EdgeEntry]: ...
    def migrations_of(self, key: Any) -> frozenset[Migratable[VersionValue]]: ...
    def has_migration(self, key: Transitional) -> bool: ...
    def get_migration(self, key: Transitional) -> Migratable[VersionValue]: ...
    def get_migration_by_edge(self, key: Transitional) -> Migratable[VersionValue]: ...
    def is_adjacent(self, key: Transitional) -> bool: ...
    def is_critical_edge(self, key: Transitional) -> bool: ...
    def has_hooks(self, key: Transitional) -> bool: ...
    def hooks(self, key: Transitional | None = None) -> list[HookRef]: ...
    def get_hooks(self, key: Transitional) -> list[HookRef]: ...


class ModelWrite(Protocol[VersionValue_co]):
    """Write-side model capability."""

    def store(self, entry: NodeEntry) -> NodeEntry: ...
    def hydrate(
        self, entry: VersionNode[VersionValue]
    ) -> VersionNode[VersionValue]: ...
    def reconcile(self, entry: NodeEntry) -> NodeEntry: ...
    def remove_model(self, key: Any) -> None: ...
    def remove_model_by_ref(self, ref: ModelRef) -> None: ...
    def clear_models(self) -> None: ...


class MigrationWrite(Protocol[VersionValue]):
    """Write-side migration capability."""

    def store_migration(
        self, entry: MigrationSpec | EdgeEntry
    ) -> EdgeEntry: ...
    def reflect(
        self,
        anchor: VersionNode[VersionValue],
        target: Comparable[VersionValue],
        migration: JsonPatch | MigrationFunc,
    ) -> VersionNode[VersionValue]: ...
    def bind(
        self,
        source: VersionNode[VersionValue],
        target: VersionNode[VersionValue],
    ) -> Any: ...
    def remove_migration(self, key: Transitional) -> None: ...
    def remove_migration_range(
        self,
        from_version: VersionNode[VersionValue],
        to_version: VersionNode[VersionValue],
    ) -> None: ...
    def clear_migrations(self) -> None: ...
    def add_hook(self, key: Transitional, hook: HookRef) -> None: ...
    def remove_hook(
        self, key: Transitional, hook: HookRef | None = None
    ) -> None: ...
    def clear_hooks(self, key: Transitional | None = None) -> None: ...


class KindWrite(Protocol):
    """Write-side kind lifecycle capability."""

    def delete_kind(self, kind: ModelKind) -> None: ...


class RegistryPort(
    GraphCatalog[VersionValue],
    ModelWrite[VersionValue],
    MigrationWrite[VersionValue],
    KindWrite,
    Protocol[VersionValue],
):
    """Full catalog contract for an in-memory or remote adapter."""

    def health(
        self,
        entity: Identifiable | None = None,
        *,
        fail_level: HealthFailLevel | None = None,
    ) -> tuple[HealthIssue, ...]: ...


__all__ = [
    "HEALTH_SEVERITY_ORDER",
    "DigestLookup",
    "GraphCatalog",
    "HealthFailLevel",
    "HealthIssue",
    "HealthSeverity",
    "KindWrite",
    "MigrationWrite",
    "ModelCatalog",
    "ModelWrite",
    "PathCatalog",
    "ReflectionPort",
    "RegistryPort",
]
