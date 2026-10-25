"""Convergence build engine: thin facade over registration and reflection."""

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
from pyverge.discovery import (
    MigrationSpec,
    ModelRegistrationMode,
    RegisterMigration,
    RegisterModel,
    RegistrationCommand,
)
from pyverge.discovery.reflection import Reflector
from pyverge.execution import (
    CompositeExtractor,
    ExecutionCoordinator,
    ExecutionPlanner,
    PathResolver,
    PolicyEngine,
    Runner,
)
from pyverge.execution.context import ExecutionEnvironment
from pyverge.execution.direction import DirectionPolicy
from pyverge.execution.middleware import BackendMiddleware
from pyverge.execution.targets import TargetCompiler
from pyverge.execution.types import BackendPort
from pyverge.migrations.identity import MigrationIdentityResolver
from pyverge.migrations.json_patch import JsonPatch
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
    BackwardCompatibilityGuard,
    Comparable,
    EdgeKey,
    Migratable,
    Transitional,
    Versionable,
    VersionEdge,
    VersionNode,
    VersionPair,
)
from pyverge.versioning.errors import BackwardCompatibilityError


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
        self.explorer = GraphExplorer(registry)

    def runner(  # noqa: PLR0913
        self,
        *,
        backend: BackendPort[VersionValue],
        middleware: tuple[BackendMiddleware, ...] = (),
        environment: ExecutionEnvironment,
        direction: DirectionPolicy,
        on_direction_violation: DirectionViolationStrategy,
        on_missing_path: VersionMissingStrategy,
        depth_limit: int,
        on_depth_violation: DepthViolationStrategy,
        validation_mode: Literal["strict", "lax", "none"],
    ) -> Runner[VersionValue]:
        """Build a runtime facade over this engine's dependencies."""
        coordinator = ExecutionCoordinator[VersionValue](
            extractor=CompositeExtractor[VersionValue](
                self.registry,
                adapter=self.adapter,
                validation_mode=validation_mode,
            ),
            paths=PathResolver[VersionValue](self.registry),
            policy=PolicyEngine[VersionValue](
                direction=direction,
                on_direction_violation=on_direction_violation,
                on_missing_path=on_missing_path,
                depth_limit=depth_limit,
                on_depth_violation=on_depth_violation,
            ),
            planner=ExecutionPlanner[VersionValue](),
        )
        return Runner[VersionValue](
            coordinator=coordinator,
            adapter=self.adapter,
            target_compiler=TargetCompiler[VersionValue](
                self.registry,
                self.adapter,
            ),
            backend=backend,
            middleware=middleware,
            environment=environment,
        )

    def copy(self) -> Engine[VersionValue]:
        """Return a build engine over a mutable copy of this registry."""
        return Engine(
            self.registry.copy(),
            self.adapter,
            self.identity_resolver,
            self.reflector,
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

    def register(self: Self, command: RegistrationCommand) -> Any:  # noqa: C901
        """Execute one registration command."""
        if isinstance(command, RegisterModel):
            payload = command.payload
            version = (
                payload
                if isinstance(payload, VersionNode)
                else self.adapter.versionable(payload)
            )
            if command.mode is ModelRegistrationMode.STRICT:
                return self.registry.store_model(version)
            return self.registry.reconcile_model(version)
        if isinstance(command, RegisterMigration):
            spec = command.spec
            v_from, v_to = spec.pair
            if v_from.kind != v_to.kind:
                raise CatalogError(
                    self.registry.name,
                    f"Cannot register migration across kinds: "
                    f"{v_from.kind} != {v_to.kind}",
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
                self.registry.store_model(resolved_from)
            if resolved_to is None:
                resolved_to = self.reflector.materialize_missing(
                    resolved_from, v_to, spec.func
                )
                self.registry.store_model(resolved_to)
            if not self.registry.is_adjacent(
                EdgeKey.from_pair(resolved_from, resolved_to)
            ):
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
                        required_additions=compatibility.required_additions(
                            diff, report
                        ),
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
        raise TypeError(f"Unsupported registration command: {command!r}")

    def store_model(self: Self, payload: Any) -> VersionNode[VersionValue]:
        return self.register(RegisterModel(payload, ModelRegistrationMode.STRICT))

    def reconcile_model(self: Self, payload: Any) -> VersionNode[VersionValue]:
        return self.register(RegisterModel(payload, ModelRegistrationMode.RECONCILE))

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
        return self.register(
            RegisterMigration(
                MigrationSpec(key, func, backward_compatible=backward_compatible)
            )
        )

    def reconstruct(
        self: Self,
        anchor: VersionNode[VersionValue],
        target: Comparable[VersionValue],
        migration: JsonPatch | MigrationFunc,
    ) -> None:
        node = self.reflector.materialize_missing(anchor, target, migration)
        self.registry.store_model(node)

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
