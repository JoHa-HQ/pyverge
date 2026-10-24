"""Convergence build engine: thin facade over registration and reflection."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Generic, Self, cast, overload

from pyverge.core.types import (
    Attachable,
    MigrationFunc,
    ModelHandle,
    ModelKind,
    VersionValue,
)
from pyverge.migration.registration import MigrationRegistrationService
from pyverge.migrations.identity import MigrationIdentityResolver
from pyverge.migrations.json_patch import JsonPatch
from pyverge.reflection import Reflector
from pyverge.reflection.types import DiffProvider
from pyverge.registry import GraphCatalog, Registry
from pyverge.registry.errors import (
    CatalogError,
    MigrationNotFoundError,
    MissingReferenceError,
    ModelNotFoundError,
)
from pyverge.registry.explorer import GraphExplorer
from pyverge.schemas.types import ModelAdapter
from pyverge.versioning import (
    Comparable,
    DiffMaterializer,
    EdgeKey,
    Migratable,
    Transitional,
    Versionable,
    VersionNode,
    VersionPair,
)


class Engine(Generic[VersionValue]):
    """Build-phase facade over catalogs, registrars, and reflection."""

    def __init__(
        self: Self,
        registry: Registry[VersionValue],
        adapter: ModelAdapter,
        identity_resolver: MigrationIdentityResolver,
        materializers: Mapping[str, DiffMaterializer[Any]],
        diff_provider: DiffProvider[VersionValue],
        on_missing: str = "raise",
    ) -> None:
        self.registry = registry
        self.adapter = adapter
        self.identity_resolver = identity_resolver
        self.materializers = dict(materializers)
        self.diff_provider = diff_provider
        self.on_missing = on_missing
        self.reflector = Reflector(
            adapter,
            diff_provider,
            self.materializers,
            on_missing=on_missing,
        )
        self.migrations = MigrationRegistrationService(
            registry,
            adapter,
            identity_resolver,
            self.reflector,
        )
        self.explorer = GraphExplorer(registry)

    def copy(self) -> Engine[VersionValue]:
        """Return a build engine over a mutable copy of this registry."""
        return Engine(
            self.registry.copy(),
            self.adapter,
            self.identity_resolver,
            self.materializers,
            self.diff_provider,
            self.on_missing,
        )

    def copy_registry(self) -> Registry[VersionValue]:
        """Return a mutable copy of the build registry."""
        return self.registry.copy()

    def snapshot(self) -> GraphCatalog:
        """Return a frozen snapshot of the current registry graph."""
        return self.explorer.snapshot()

    def lock(self) -> GraphCatalog:
        """Freeze this build registry and return the runtime snapshot."""
        return cast("GraphCatalog", self.registry.lock())

    def explore(self) -> GraphExplorer[VersionValue]:
        """Return build-mode graph queries without constructing a runtime."""
        return self.explorer

    def __contains__(self, index: Any) -> bool:
        try:
            return index in self.registry
        except (ModelNotFoundError, MigrationNotFoundError, CatalogError, TypeError):
            return False

    @overload
    def __getitem__(
        self, index: Versionable[VersionValue]
    ) -> Versionable[VersionValue]: ...
    @overload
    def __getitem__(
        self, index: Migratable[VersionValue]
    ) -> Migratable[VersionValue]: ...
    @overload
    def __getitem__(self, index: EdgeKey[VersionValue]) -> Migratable[VersionValue]: ...
    def __getitem__(
        self, index: Any
    ) -> Versionable[VersionValue] | Migratable[VersionValue]:
        return self.registry[index]

    def store_model(
        self: Self, version: VersionNode[VersionValue]
    ) -> VersionNode[VersionValue]:
        return self.registry.store_model(version)

    def reconcile_model(
        self: Self, version: VersionNode[VersionValue]
    ) -> VersionNode[VersionValue]:
        return self.registry.reconcile_model(version)

    def validate(self: Self, key: Comparable[VersionValue] | None = None) -> None:
        versions = (
            self.registry.versions if key is None else [self.registry.get_model(key)]
        )
        for version in versions:
            absent = self.registry.missing_references(version)
            if absent:
                raise MissingReferenceError(
                    self.registry.name,
                    version.version,
                    absent,
                )

    def get_model(
        self: Self, key: Comparable[VersionValue]
    ) -> VersionNode[VersionValue]:
        return self.registry.get_model(key)

    def get_model_by_class(self: Self, cls: ModelHandle) -> VersionNode[VersionValue]:
        return self.registry.get_model_by_handle(cls)

    def remove_model_by_class(self: Self, cls: ModelHandle) -> None:
        self.registry.remove_model_by_handle(cls)

    def remove_model(self: Self, key: Comparable[VersionValue]) -> None:
        self.registry.remove_model(key)

    def get_latest_model(self: Self, kind: ModelKind) -> VersionNode[VersionValue]:
        return self.registry.latest(kind)

    def get_earliest_model(self: Self, kind: ModelKind) -> VersionNode[VersionValue]:
        return self.registry.earliest(kind)

    def get_entities(self: Self) -> list[ModelKind]:
        return self.registry.entities

    def store_migration(
        self: Self,
        key: VersionPair[VersionValue],
        func: MigrationFunc,
        *,
        backward_compatible: bool = False,
    ) -> MigrationFunc:
        return self.migrations.store(
            key,
            func,
            backward_compatible=backward_compatible,
        )

    def reconstruct(
        self: Self,
        anchor: VersionNode[VersionValue],
        target: Comparable[VersionValue],
        migration: JsonPatch | MigrationFunc,
    ) -> None:
        self.migrations.reconstruct(anchor, target, migration)

    def propose_migration(
        self: Self,
        source: VersionNode[VersionValue],
        target: VersionNode[VersionValue],
    ) -> Any:
        return self.migrations.propose(source, target)

    def get_migration(self: Self, key: Transitional[VersionValue]) -> Migratable:
        return self.migrations.get(key)

    def remove_migration(
        self: Self,
        key: Transitional[VersionValue],
        *,
        force: bool = False,
    ) -> None:
        self.migrations.remove(key, force=force)

    def remove_migration_range(
        self: Self,
        from_version: Versionable,
        to_version: Versionable,
    ) -> None:
        self.migrations.remove_range(from_version, to_version)

    def delete_kind(self: Self, kind: ModelKind) -> None:
        self.migrations.delete_kind(kind)

    def find_migration_path(
        self: Self,
        from_version: Versionable,
        to_version: Versionable,
    ) -> list[tuple[VersionNode[VersionValue], VersionNode[VersionValue]]]:
        return self.migrations.path(from_version, to_version)

    def add_hook(self: Self, key: Transitional[VersionValue], hook: Attachable) -> None:
        self.migrations.add_hook(key, hook)

    def remove_hook(
        self: Self,
        key: Transitional[VersionValue],
        hook: Attachable | None = None,
    ) -> None:
        self.migrations.remove_hook(key, hook)

    def clear_hooks(self: Self, key: Transitional[VersionValue] | None = None) -> None:
        self.migrations.clear_hooks(key)
