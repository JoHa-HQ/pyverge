from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Generic, Self, cast, overload

from pyverge.core.graph import GraphBuilder, MigrationGraph, Revision
from pyverge.core.registry import HealthFailLevel, HealthIssue, Registry
from pyverge.core.registry.errors import (
    CatalogError,
    MigrationNotFoundError,
    MissingReferenceError,
    ModelNotFoundError,
)
from pyverge.core.types import (
    MigrationFunc,
    ModelHandle,
    ModelKind,
    VersionValue,
)
from pyverge.core.versioning import (
    Comparable,
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
    VersionPair,
)
from pyverge.migrations import MigrationSpec
from pyverge.migrations.json_patch import JsonPatch
from pyverge.schemas.types import ModelAdapter


class Engine(Generic[VersionValue]):
    """A namespaced build-time facade for a versioned migration graph.

    The Engine owns exactly one :class:`Registry` and one
    :class:`ModelAdapter`. The adapter's ``ModelCodec`` fixes the Engine
    namespace and supplies model identity. Namespace consistency is preserved
    by the registry, ``EdgeKey`` endpoint validation, and single-namespace
    graph snapshots.

    The Engine coordinates build-time operations:

    - registering, hydrating, and reconciling models or key-only entries;
    - validating registry health and descriptor references;
    - delegating migration registration, reflection, and binding to the
      Registry;
    - building immutable graph snapshots;

    It does not execute migrations; :class:`~pyverge.runtime.Runner` does.
    Migration registration, reflection, identity assignment, and compatibility
    linting belong to :class:`~pyverge.core.registry.Registry`.

    Args:
        registry: Mutable registry owned by this Engine.
        adapter: Provider adapter for model identity and materialization.
    """

    def __init__(
        self: Self,
        registry: Registry[VersionValue],
        adapter: ModelAdapter,
    ) -> None:
        self.registry = registry
        self.adapter = adapter

    @property
    def namespace(self: Self) -> str:
        return getattr(self.adapter, "model_codec").namespace

    @property
    def versions(self: Self) -> list[VersionNode[VersionValue]]:
        return self.registry.versions

    @property
    def model_count(self: Self) -> int:
        return len(self.registry.versions)

    @property
    def kinds(self: Self) -> list[ModelKind]:
        return self.registry.kinds

    @property
    def migration_count(self: Self) -> int:
        return sum(len(self.registry.migrations(kind)) for kind in self.kinds)

    def list_versions(
        self: Self,
        kind: ModelKind | None = None,
    ) -> list[VersionNode[VersionValue]]:
        if kind is None:
            return self.registry.versions
        return self.registry.kind_versions(kind)

    def get_model_by_ref(self: Self, ref: ModelRef) -> VersionNode[VersionValue]:
        return self.registry.get_model_by_ref(ref)

    def attach_hooks(self: Self, hooks: Iterable[HookRef]) -> None:
        for kind in self.registry.kinds:
            for edge in self.registry.migrations(kind):
                for hook in hooks:
                    self.registry.add_hook(edge, hook)

    def copy(self) -> Engine[VersionValue]:
        return Engine(self.registry.copy(), self.adapter)

    def copy_registry(self) -> Registry[VersionValue]:
        return self.registry.copy()

    def snapshot(
        self,
        revision: Revision | None = None,
    ) -> MigrationGraph[VersionValue]:
        return GraphBuilder[VersionValue]().build(
            self.registry,
            revision=revision,
        )

    def __contains__(self, index: Any) -> bool:
        """Return whether the registry recognizes an index.

        Args:
            index: Model key, edge key, or another registry index.

        Returns:
            bool: ``True`` when the registry contains the index, otherwise
                ``False``.
        """
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
        return cast(
            "Versionable[VersionValue] | Migratable[VersionValue]",
            self.registry[index],
        )

    def store_model(self: Self, payload: Any) -> NodeEntry:
        """Store a key or node, upgrading and reconciling as needed."""
        entry = (
            payload
            if isinstance(payload, VersionKey)
            else self.adapter.versionable(payload)
        )
        if isinstance(entry, VersionNode):
            return self.registry.hydrate(entry)
        existing = self.registry.find_entry(entry)
        if existing is not None:
            return existing
        return self.registry.store(entry)

    def reconcile_model(self: Self, payload: Any) -> VersionNode[VersionValue]:
        version = (
            payload
            if isinstance(payload, VersionKey)
            else self.adapter.versionable(payload)
        )
        return cast("VersionNode[VersionValue]", self.registry.reconcile(version))

    def health(
        self: Self,
        entity: Identifiable | None = None,
        *,
        fail_level: HealthFailLevel | None = None,
    ) -> tuple[HealthIssue, ...]:
        """Return health issues from the owning registry.

        Args:
            entity: Node or edge identity to inspect. ``None`` inspects every
                cached entity.
            fail_level: When set, raise when an issue meets or exceeds this
                severity.

        Returns:
            tuple[HealthIssue, ...]: Health issues for the entity or registry.
        """
        return self.registry.health(entity, fail_level=fail_level)

    def validate(self: Self, key: Comparable[VersionValue] | None = None) -> None:
        if key is None:
            versions = self.registry.versions
        elif isinstance(key, VersionNode):
            versions = [key]
        else:
            versions = [self.registry.get_model(key)]
        for version in versions:
            absent = frozenset(
                issue.details["reference"]
                for issue in self.registry.health(version)
                if issue.code.startswith("reference.missing.")
            )
            if absent:
                raise MissingReferenceError(self.registry.namespace, version, absent)

    def get_model(
        self: Self, key: Comparable[VersionValue]
    ) -> VersionNode[VersionValue]:
        return self.registry.get_model(key)

    def get_model_by_class(self: Self, cls: ModelHandle) -> VersionNode[VersionValue]:
        return self.registry.get_model_by_ref(self.adapter.ref(cls))

    def remove_model_by_class(self: Self, cls: ModelHandle) -> None:
        self.registry.remove_model_by_ref(self.adapter.ref(cls))

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
        discriminator: str = "default",
    ) -> EdgeEntry:
        return self.registry.store_migration(
            MigrationSpec(
                key,
                func,
                backward_compatible=backward_compatible,
                discriminator=discriminator,
            )
        )

    def reconstruct(
        self: Self,
        anchor: VersionNode[VersionValue],
        target: Comparable[VersionValue],
        migration: JsonPatch | MigrationFunc,
    ) -> None:
        self.registry.store(self.registry.reflect(anchor, target, migration))

    def propose_migration(
        self: Self,
        source: VersionNode[VersionValue],
        target: VersionNode[VersionValue],
    ) -> Any:
        return self.registry.bind(source, target)

    def get_migration(self: Self, key: Transitional[VersionValue]) -> Migratable:
        return self.registry.get_migration_by_edge(key)

    def remove_migration(
        self: Self,
        key: Transitional[VersionValue],
        *,
        force: bool = False,
    ) -> None:
        registry = self.registry
        edge = registry.get_migration_by_edge(key)
        if not force:
            if not registry.is_adjacent(key):
                raise CatalogError(
                    registry.namespace,
                    f"Cannot remove migration {key.source}→{key.target}: "
                    "it is not adjacent to any other version.",
                )
            if registry.is_critical_edge(key):
                raise CatalogError(
                    registry.namespace,
                    f"Cannot remove critical migration {key.source}→{key.target}. "
                    "It is on the critical path. Use force=True to override.",
                )
        registry.remove_migration(EdgeKey.from_version_edge(edge))

    def remove_migration_range(
        self: Self,
        from_version: Versionable,
        to_version: Versionable,
    ) -> None:
        self.registry.remove_migration_range(from_version, to_version)

    def delete_kind(self: Self, kind: ModelKind) -> None:
        self.registry.delete_kind(kind)

    def find_migration_path(
        self: Self,
        from_version: Versionable,
        to_version: Versionable,
    ) -> list[tuple[VersionNode[VersionValue], VersionNode[VersionValue]]]:
        return self.snapshot().migration_path(from_version, to_version)

    def add_hook(self: Self, key: Transitional[VersionValue], hook: HookRef) -> None:
        registry = self.registry
        edge = registry.get_migration_by_edge(key)
        registry.add_hook(edge, hook)

    def remove_hook(
        self: Self,
        key: Transitional[VersionValue],
        hook: HookRef | None = None,
    ) -> None:
        registry = self.registry
        edge = registry.get_migration_by_edge(key)
        registry.remove_hook(edge, hook)

    def clear_hooks(self: Self, key: Transitional[VersionValue] | None = None) -> None:
        if key is None:
            self.registry.clear_hooks()
        else:
            edge = self.registry.get_migration_by_edge(key)
            self.registry.clear_hooks(edge)
