"""Migration registration service."""

from __future__ import annotations

from typing import Any, Generic

from pyverge.core.types import (
    Attachable,
    MigrationFunc,
    ModelKind,
    VersionValue,
)
from pyverge.migration.errors import BackwardCompatibilityError
from pyverge.migrations.identity import MigrationIdentityResolver
from pyverge.reflection import Reflector
from pyverge.registry import RegistryPort
from pyverge.registry.errors import CatalogError, ModelNotFoundError
from pyverge.schemas.types import ModelAdapter
from pyverge.versioning import (
    Comparable,
    CompatibilityReport,
    EdgeKey,
    Migratable,
    Transitional,
    Versionable,
    VersionEdge,
    VersionNode,
    VersionPair,
)


class MigrationRegistrationService(Generic[VersionValue]):
    """Register migrations, manage hooks, and resolve endpoints."""

    def __init__(
        self,
        registry: RegistryPort,
        adapter: ModelAdapter,
        identity_resolver: MigrationIdentityResolver,
        reflector: Reflector[VersionValue],
    ) -> None:
        self._registry = registry
        self._adapter = adapter
        self._identity_resolver = identity_resolver
        self._reflector = reflector

    def store(
        self,
        key: VersionPair[VersionValue],
        func: MigrationFunc,
        *,
        backward_compatible: bool = False,
    ) -> MigrationFunc:
        registry = self._registry
        v_from, v_to = key
        if v_from.kind != v_to.kind:
            raise CatalogError(
                registry.name,
                f"Cannot register migration across kinds: {v_from.kind} != {v_to.kind}",
            )
        resolved_from = self._resolve(v_from, other=v_to, func=func)
        resolved_to = self._resolve(v_to, other=v_from, func=func)
        if not registry.is_adjacent(EdgeKey.from_pair(resolved_from, resolved_to)):
            raise CatalogError(
                registry.name,
                f"Cannot register migration with skip versions: {v_from}→{v_to}",
            )
        diff = self._adapter.diff(resolved_from, resolved_to)
        if backward_compatible:
            report = CompatibilityReport.from_diff(
                diff,
                identity_fields=frozenset(
                    {self._adapter.kind_property, self._adapter.version_property}
                ),
            )
            if report.structural_breaking:
                raise BackwardCompatibilityError(
                    registry.name,
                    (resolved_from, resolved_to),
                    removed=tuple(report.removed_fields),
                    modified=tuple(report.modified_fields),
                    required_additions=tuple(
                        field
                        for field in report.added_fields
                        if diff.is_added_required(field)
                    ),
                )
        registry.store_migration(
            VersionEdge(
                source=resolved_from,
                target=resolved_to,
                diff=diff,
                func=func,
                migration=self._identity_resolver.resolve(func),
            )
        )
        return func

    def _resolve(
        self,
        endpoint: Comparable[VersionValue],
        *,
        other: Comparable[VersionValue],
        func: MigrationFunc,
    ) -> VersionNode[VersionValue]:
        try:
            return self._registry.get_model(endpoint)
        except ModelNotFoundError:
            pass
        try:
            anchor = self._registry.get_model(other)
        except ModelNotFoundError:
            raise ModelNotFoundError(self._registry.name, endpoint.version)
        node = self._reflector.materialize_missing(anchor, endpoint, func)
        self._registry.store_model(node)
        return node

    def reconstruct(
        self,
        anchor: VersionNode[VersionValue],
        target: Comparable[VersionValue],
        migration: Any,
    ) -> None:
        node = self._reflector.materialize_missing(anchor, target, migration)
        self._registry.store_model(node)

    def propose(
        self, source: VersionNode[VersionValue], target: VersionNode[VersionValue]
    ) -> Any:
        return self._reflector.propose(source, target)

    def get(self, key: Transitional[VersionValue]) -> Migratable:
        return self._registry.get_migration_by_edge(key)

    def remove(self, key: Transitional[VersionValue], *, force: bool = False) -> None:
        edge = self._registry.get_migration_by_edge(key)
        if not force:
            if not self._registry.is_adjacent(key):
                raise CatalogError(
                    self._registry.name,
                    f"Cannot remove migration {key.source}→{key.target}: "
                    "it is not adjacent to any other version.",
                )
            if self._registry.is_critical_edge(key):
                raise CatalogError(
                    self._registry.name,
                    f"Cannot remove critical migration {key.source}→{key.target}. "
                    "It is on the critical path. Use force=True to override.",
                )
        self._registry.remove_migration(EdgeKey.from_version_edge(edge))

    def remove_range(self, from_version: Versionable, to_version: Versionable) -> None:
        self._registry.remove_migration_range(from_version, to_version)

    def delete_kind(self, kind: ModelKind) -> None:  # noqa: C901
        registry = self._registry
        versions = registry.kind_versions(kind)
        if not versions:
            return
        version_set = set(versions)
        for v in versions:
            for edge in registry.migrations_of(v):
                if edge.source not in version_set or edge.target not in version_set:
                    raise CatalogError(
                        registry.name,
                        f"Cannot delete kind '{kind}': version is referenced "
                        f"by cross-kind migration {edge.source}→{edge.target}",
                    )
        for v in versions:
            for edge in list(registry.migrations_of(v)):
                if edge.source in version_set and edge.target in version_set:
                    if registry.has_hooks(edge):
                        registry.clear_hooks(edge)
                    registry.remove_migration(EdgeKey.from_version_edge(edge))
        for v in reversed(versions):
            try:
                registry.remove_model(v)
            except CatalogError:
                pass

    def path(self, from_version: Versionable, to_version: Versionable) -> list[Any]:
        return self._registry.migration_path(from_version, to_version)

    def add_hook(self, key: Transitional[VersionValue], hook: Attachable) -> None:
        edge = self._registry.get_migration_by_edge(key)
        self._registry.add_hook(edge, hook)

    def remove_hook(
        self, key: Transitional[VersionValue], hook: Attachable | None = None
    ) -> None:
        edge = self._registry.get_migration_by_edge(key)
        self._registry.remove_hook(edge, hook)

    def clear_hooks(self, key: Transitional[VersionValue] | None = None) -> None:
        if key is None:
            self._registry.clear_hooks()
        else:
            edge = self._registry.get_migration_by_edge(key)
            self._registry.clear_hooks(edge)


__all__ = ["MigrationRegistrationService"]
