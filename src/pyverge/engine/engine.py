from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic, Literal, Self, cast, overload

from pyverge.core.types import (
    Attachable,
    DepthViolationStrategy,
    DirectionViolationStrategy,
    MigrationFunc,
    ModelHandle,
    ModelKind,
    RegistrationMode,
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
from pyverge.migrations.identity import MigrationIdentityResolver
from pyverge.migrations.json_patch import JsonPatch
from pyverge.registry import Registry
from pyverge.registry.errors import (
    CatalogError,
    MigrationNotFoundError,
    MissingReferenceError,
    ModelNotFoundError,
)
from pyverge.schemas.types import ModelAdapter
from pyverge.versioning import (
    BackwardCompatibilityGuard,
    Comparable,
    EdgeKey,
    Migratable,
    NodeEntry,
    Transitional,
    Versionable,
    VersionEdge,
    VersionKey,
    VersionNode,
    VersionPair,
)
from pyverge.versioning.errors import BackwardCompatibilityError

from .reflector import Reflector


@dataclass(frozen=True, slots=True)
class RunnerOptions(Generic[VersionValue]):
    """Inputs needed to build a runtime runner."""

    backend: BackendPort[VersionValue]
    environment: ExecutionEnvironment
    direction: DirectionPolicy
    on_direction_violation: DirectionViolationStrategy
    on_missing_path: VersionMissingStrategy
    depth_limit: int
    on_depth_violation: DepthViolationStrategy
    validation_mode: Literal["strict", "lax", "none"]
    middleware: tuple[BackendMiddleware, ...] = ()


class Engine(Generic[VersionValue]):
    """Build-phase facade over catalogs, registrars, and reflection."""

    def __init__(
        self: Self,
        registry: Registry[VersionValue],
        adapter: ModelAdapter,
        identity_resolver: MigrationIdentityResolver,
        reflector: Reflector[VersionValue],
    ) -> None:
        self.registry = registry
        self.adapter = adapter
        self.identity_resolver = identity_resolver
        self.reflector = reflector

    def runner(self, options: RunnerOptions[VersionValue]) -> Runner[VersionValue]:
        graph = self.snapshot()
        bindings = MigrationBindings[VersionValue].from_catalog(self.registry)
        coordinator = ExecutionCoordinator[VersionValue](
            extractor=PayloadWalker[VersionValue](
                graph,
                adapter=self.adapter,
                validation_mode=options.validation_mode,
            ),
            finder=PathFinder[VersionValue](
                graph=graph,
                targets=TargetCompiler[VersionValue](graph, self.adapter),
                migrations=bindings,
                policy=PolicyEngine[VersionValue](
                    direction=options.direction,
                    on_direction_violation=options.on_direction_violation,
                    on_missing_path=options.on_missing_path,
                    depth_limit=options.depth_limit,
                    on_depth_violation=options.on_depth_violation,
                ),
            ),
            planner=ExecutionPlanner[VersionValue](),
        )
        return Runner[VersionValue](
            coordinator=coordinator,
            adapter=self.adapter,
            backend=options.backend,
            middleware=options.middleware,
            environment=options.environment,
        )

    def copy(self) -> Engine[VersionValue]:
        return Engine(
            self.registry.copy(),
            self.adapter,
            self.identity_resolver,
            self.reflector,
        )

    def copy_registry(self) -> Registry[VersionValue]:
        return self.registry.copy()

    def snapshot(self) -> MigrationGraph[VersionValue]:
        return GraphBuilder[VersionValue]().build(self.registry)

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
        return cast(
            "Versionable[VersionValue] | Migratable[VersionValue]",
            self.registry[index],
        )

    def _register_migration(self: Self, spec: MigrationSpec) -> MigrationFunc:
        v_from, v_to = spec.pair
        if v_from.kind != v_to.kind:
            raise CatalogError(
                self.registry.name,
                f"Cannot register migration across kinds: {v_from.kind} != {v_to.kind}",
            )
        resolved_from = self.registry.find_model(v_from)
        resolved_to = self.registry.find_model(v_to)
        if resolved_from is None and resolved_to is None:
            raise ModelNotFoundError(self.registry.name, v_from.version)
        if resolved_from is None:
            assert resolved_to is not None
            resolved_from = self.reflector.materialize_missing(
                resolved_to, v_from, spec.func
            )
            self._store_node(resolved_from, mode="strict")
        if resolved_to is None:
            resolved_to = self.reflector.materialize_missing(
                resolved_from, v_to, spec.func
            )
            self._store_node(resolved_to, mode="strict")
        if not self.registry.is_adjacent(EdgeKey.from_pair(resolved_from, resolved_to)):
            raise CatalogError(
                self.registry.name,
                f"Cannot register migration with skip versions: {v_from}→{v_to}",
            )
        diff = self.adapter.diff(resolved_from, resolved_to)
        if spec.backward_compatible:
            compatibility = BackwardCompatibilityGuard(
                frozenset(
                    {
                        self.adapter.kind_property,
                        self.adapter.version_property,
                    }
                )
            )
            report = compatibility.evaluate(diff)
            if report.structural_breaking:
                raise BackwardCompatibilityError(
                    self.registry.name,
                    (resolved_from, resolved_to),
                    removed=tuple(report.removed_fields),
                    modified=tuple(report.modified_fields),
                    required_additions=compatibility.required_additions(diff, report),
                )
        self.registry.store_migration(
            VersionEdge(
                source=resolved_from,
                target=resolved_to,
                diff=diff,
                func=spec.func,
                migration=self.identity_resolver.resolve(spec.func),
            )
        )
        return spec.func

    def _store_node(
        self: Self,
        version: NodeEntry,
        *,
        mode: RegistrationMode,
    ) -> VersionNode[VersionValue]:
        stored = (
            self.registry.store(version)
            if mode == "strict"
            else self.registry.reconcile(version)
        )
        return cast("VersionNode[VersionValue]", stored)

    def store_model(self: Self, payload: Any) -> NodeEntry:
        """Store a key or node, upgrading and reconciling as needed."""
        if isinstance(payload, VersionNode):
            return self.registry.hydrate(payload)
        if isinstance(payload, VersionKey):
            existing = self.registry.find_entry(payload)
            if existing is not None:
                return existing
            return self.registry.store(payload)
        return self.registry.hydrate(self.adapter.versionable(payload))

    def reconcile_model(self: Self, payload: Any) -> VersionNode[VersionValue]:
        version = (
            payload
            if isinstance(payload, VersionKey)
            else self.adapter.versionable(payload)
        )
        return self._store_node(version, mode="reconcile")

    def validate(self: Self, key: Comparable[VersionValue] | None = None) -> None:
        if key is None:
            versions = self.registry.versions
        elif isinstance(key, VersionNode):
            versions = [key]
        else:
            versions = [self.registry.get_model(key)]
        for version in versions:
            absent = self.registry.missing_references(version, require_registered=False)
            if absent:
                raise MissingReferenceError(
                    self.registry.name,
                    version,
                    absent,
                )

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
        return self._register_migration(
            MigrationSpec(key, func, backward_compatible=backward_compatible)
        )

    def reconstruct(
        self: Self,
        anchor: VersionNode[VersionValue],
        target: Comparable[VersionValue],
        migration: JsonPatch | MigrationFunc,
    ) -> None:
        node = self.reflector.materialize_missing(anchor, target, migration)
        self._store_node(node, mode="strict")

    def propose_migration(
        self: Self,
        source: VersionNode[VersionValue],
        target: VersionNode[VersionValue],
    ) -> Any:
        return self.reflector.propose(source, target)

    def get_migration(self: Self, key: Transitional[VersionValue]) -> Migratable:
        return self.registry.get_migration_by_edge(key)

    def remove_migration(
        self: Self,
        key: Transitional[VersionValue],
        *,
        force: bool = False,
    ) -> None:
        edge = self.registry.get_migration_by_edge(key)
        if not force:
            if not self.registry.is_adjacent(key):
                raise CatalogError(
                    self.registry.name,
                    f"Cannot remove migration {key.source}→{key.target}: "
                    "it is not adjacent to any other version.",
                )
            if self.registry.is_critical_edge(key):
                raise CatalogError(
                    self.registry.name,
                    f"Cannot remove critical migration {key.source}→{key.target}. "
                    "It is on the critical path. Use force=True to override.",
                )
        self.registry.remove_migration(EdgeKey.from_version_edge(edge))

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
        return self.registry.migration_path(from_version, to_version)

    def add_hook(self: Self, key: Transitional[VersionValue], hook: Attachable) -> None:
        edge = self.registry.get_migration_by_edge(key)
        self.registry.add_hook(edge, hook)

    def remove_hook(
        self: Self,
        key: Transitional[VersionValue],
        hook: Attachable | None = None,
    ) -> None:
        edge = self.registry.get_migration_by_edge(key)
        self.registry.remove_hook(edge, hook)

    def clear_hooks(self: Self, key: Transitional[VersionValue] | None = None) -> None:
        if key is None:
            self.registry.clear_hooks()
        else:
            edge = self.registry.get_migration_by_edge(key)
            self.registry.clear_hooks(edge)
