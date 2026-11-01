from __future__ import annotations

from typing import Any, Generic, Literal, Self, cast, overload

from pyverge.core.types import (
    Attachable,
    DepthViolationStrategy,
    DirectionViolationStrategy,
    MigrationFunc,
    ModelHandle,
    ModelKind,
    VersionMissingStrategy,
    VersionValue,
)
from pyverge.execution import (
    ExecutionCoordinator,
    ExecutionPlanner,
    PayloadWalker,
    Runner,
)
from pyverge.execution.context import ExecutionEnvironment
from pyverge.execution.middleware import BackendMiddleware
from pyverge.execution.migrations import MigrationBindings
from pyverge.execution.types import BackendPort
from pyverge.graph import (
    DirectionPolicy,
    GraphBuilder,
    MigrationGraph,
    PathFinder,
    PolicyEngine,
    TargetCompiler,
)
from pyverge.migrations import MigrationSpec
from pyverge.migrations.json_patch import JsonPatch
from pyverge.registry import HealthIssue, Registry
from pyverge.registry.errors import (
    CatalogError,
    MigrationNotFoundError,
    MissingReferenceError,
    ModelNotFoundError,
)
from pyverge.schemas.types import ModelAdapter
from pyverge.versioning import (
    Comparable,
    EdgeKey,
    Migratable,
    NodeEntry,
    Transitional,
    Versionable,
    VersionKey,
    VersionNode,
    VersionPair,
)


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
    - resolving executable migration bindings and constructing runtime runners.

    It does not execute migrations; :class:`~pyverge.execution.Runner` does.
    Migration registration, reflection, identity assignment, and compatibility
    linting belong to :class:`~pyverge.registry.Registry`.

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

    def runner(  # noqa: PLR0913
        self: Self,
        *,
        backend: BackendPort[VersionValue],
        environment: ExecutionEnvironment,
        direction: DirectionPolicy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
        depth_limit: int,
        on_depth_violation: DepthViolationStrategy,
        validation_mode: Literal["strict", "lax", "none"],
        middleware: tuple[BackendMiddleware, ...] = (),
    ) -> Runner[VersionValue]:
        graph = self.snapshot()
        bindings = MigrationBindings[VersionValue].from_catalog(self.registry)
        coordinator = ExecutionCoordinator[VersionValue](
            extractor=PayloadWalker[VersionValue](
                graph,
                adapter=self.adapter,
                validation_mode=validation_mode,
            ),
            finder=PathFinder[VersionValue](
                graph=graph,
                targets=TargetCompiler[VersionValue](graph, self.adapter),
                migrations=bindings,
                policy=PolicyEngine[VersionValue](
                    direction=direction,
                    on_direction_violation=on_direction_violation,
                    on_missing_path=on_missing_path,
                    depth_limit=depth_limit,
                    on_depth_violation=on_depth_violation,
                ),
            ),
            planner=ExecutionPlanner[VersionValue](),
        )
        return Runner[VersionValue](
            coordinator=coordinator,
            adapter=self.adapter,
            backend=backend,
            middleware=middleware,
            environment=environment,
        )

    def copy(self) -> Engine[VersionValue]:
        return Engine(self.registry.copy(), self.adapter)

    def copy_registry(self) -> Registry[VersionValue]:
        return self.registry.copy()

    def snapshot(self) -> MigrationGraph[VersionValue]:
        return GraphBuilder[VersionValue]().build(self.registry)

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
        entity: Comparable[VersionValue] | Transitional[VersionValue],
    ) -> tuple[HealthIssue, ...]:
        """Return health issues from the owning registry.

        Args:
            entity: Node or edge identity to inspect.

        Returns:
            tuple[HealthIssue, ...]: Health issues for the entity.
        """
        return self.registry.health(entity)

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
    ) -> MigrationFunc:
        return cast(
            "MigrationFunc",
            self.registry.store_migration(
                MigrationSpec(key, func, backward_compatible=backward_compatible)
            ),
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

    def add_hook(self: Self, key: Transitional[VersionValue], hook: Attachable) -> None:
        registry = self.registry
        edge = registry.get_migration_by_edge(key)
        registry.add_hook(edge, hook)

    def remove_hook(
        self: Self,
        key: Transitional[VersionValue],
        hook: Attachable | None = None,
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
