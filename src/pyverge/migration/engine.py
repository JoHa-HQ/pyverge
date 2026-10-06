from typing import Any, Generic, Self, overload

from pyverge.core.exceptions import (
    MigrationNotFoundError,
    MissingReferenceError,
    ModelNotFoundError,
    RegistryError,
)
from pyverge.core.settings import MigrationSettings
from pyverge.core.types import (
    Attachable,
    Comparable,
    DirectionViolationStrategy,
    Migratable,
    MigrationDirectionStrategy,
    MigrationFunc,
    ModelData,
    ModelHandle,
    ModelKind,
    TargetResolver,
    Transitional,
    Versionable,
    VersionMissingStrategy,
    VersionPair,
    VersionValue,
)
from pyverge.core.versioning import (
    SentinelEdge,
    VersionEdge,
)
from pyverge.migration.types import (
    Executor,
    MigrationEntry,
)
from pyverge.providers.json_patch import JsonPatch
from pyverge.providers.json_patch.migration import JsonPatchMigration
from pyverge.providers.types import (
    ModelAdapter,
)
from pyverge.reflection.discovery import CompositeDiffDiscovery, DiffDiscovery
from pyverge.reflection.reconstruction import (
    MigrationReflection,
    Reconstruction,
    ReconstructionStrategy,
    strategy_for,
)
from pyverge.reflection.reflection import Reflection

from .graph import GraphBuilder
from .registry import Registry
from .strategy import DefaultMigrationEntry


class Engine(Generic[VersionValue]):
    """Convergent migration driven by an inferred dependency graph.

    Treats ``(kind, version)`` as the first-class axis: it scans a payload for
    versioned entries, builds a graph from the migrations touching each, and
    converges every entry to a target version. Nested entries converge on their
    own terms; the graph orders children before parents. A container model is
    optional (a typed one prunes branches via precomputed shape metrics).
    """

    def __init__(
        self: Self,
        registry: Registry[VersionValue],
        settings: MigrationSettings,
        default_executor: Executor[VersionValue],
        graph_builder: GraphBuilder[VersionValue],
        adapter: ModelAdapter,
        entry_migration: MigrationEntry[VersionValue] | None = None,
    ) -> None:
        self.registry = registry
        self.settings = settings
        self.graph_builder = graph_builder
        self.default_executor = default_executor
        self.adapter = adapter
        self.entry_migration = entry_migration or DefaultMigrationEntry()
        self.discovery: DiffDiscovery[VersionValue, JsonPatch | MigrationFunc] = (
            CompositeDiffDiscovery()
        )

    def __contains__(self, index: Any) -> bool:
        """Check membership of a typed model version or migration edge.

        Typed only: fluent keys (raw tuples, bare model classes) and slices are
        sugar the manager owns.
        """
        try:
            return index in self.registry
        except (ModelNotFoundError, MigrationNotFoundError, RegistryError, TypeError):
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
    def __getitem__(
        self, index: SentinelEdge[VersionValue]
    ) -> Migratable[VersionValue]: ...

    def __getitem__(
        self, index: Any
    ) -> Versionable[VersionValue] | Migratable[VersionValue]:
        """Select a typed model version or migration."""
        return self.registry[index]

    def store_model(
        self: Self,
        version: Versionable[VersionValue],
    ) -> Versionable[VersionValue]:
        """Register a model version via the strict store.

        A duplicate ``(kind, version)`` fails loudly — re-registration is a
        caller error.  Use :meth:`reconcile_model` for an idempotent fallback.
        """
        return self.registry.store_model(version)

    def reconcile_model(
        self: Self,
        version: Versionable[VersionValue],
    ) -> Versionable[VersionValue]:
        """Register a model version, treating an identical re-registration as a
        no-op and raising :class:`ModelConflictError` on a differing surface.
        """
        return self.registry.reconcile_model(version)

    def validate(
        self: Self,
        version: Versionable[VersionValue] | None = None,
    ) -> None:
        """Validate that registered models' declared references are registered.

        With *version*, only that node is checked; otherwise the whole registry.
        Raises :class:`MissingReferenceError` naming the absent references.
        """
        nodes = (
            [self.registry.get_model(version)]
            if version is not None
            else list(self.registry.versions)
        )
        for node in nodes:
            absent = self.registry.missing_references(node)
            if absent:
                raise MissingReferenceError(
                    self.registry.name,
                    node.version,
                    absent,
                )

    def get_model(
        self: Self,
        key: Comparable[VersionValue],
    ) -> Versionable[VersionValue]:
        """Return the model matching *key*."""
        return self.registry.get_model(key)

    def get_model_by_class(
        self: Self,
        cls: ModelHandle,
    ) -> Versionable[VersionValue]:
        """Return the model matching *cls*, resolving through the adapter."""
        if not self.adapter.identify(cls):
            raise ModelNotFoundError(self.registry.name, cls)
        return self.registry.get_model_by_handle(cls)

    def remove_model_by_class(self: Self, cls: ModelHandle) -> None:
        """Remove the model matching *cls*, resolving through the adapter."""
        if not self.adapter.identify(cls):
            raise ModelNotFoundError(self.registry.name, cls)
        self.registry.remove_model_by_handle(cls)

    def remove_model(
        self: Self,
        key: Comparable[VersionValue],
    ) -> None:
        """Remove a model version from the registry."""
        self.registry.remove_model(key)

    def get_latest_model(
        self: Self,
        kind: ModelKind,
    ) -> Versionable[VersionValue]:
        """Most recent version for *kind*."""
        return self.registry.latest(kind)

    def get_earliest_model(
        self: Self,
        kind: ModelKind,
    ) -> Versionable[VersionValue]:
        """Earliest version for *kind*."""
        return self.registry.earliest(kind)

    def store_migration(
        self: Self,
        key: VersionPair[VersionValue],
        func: MigrationFunc,
        *,
        backward_compatible: bool = False,
    ) -> MigrationFunc:
        """Register a migration, validating adjacency and cross-kind endpoints.

        An endpoint without a concrete model is reconstructed when
        ``settings.on_missing == "reconstruct_model"``, else
        ``ModelNotFoundError``.
        """
        registry = self.registry
        v_from, v_to = key

        if v_from.kind != v_to.kind:
            raise RegistryError(
                registry.name,
                f"Cannot register migration across kinds: {v_from.kind} != {v_to.kind}",
            )

        resolved_from = self._resolve(v_from, other=v_to, func=func)
        resolved_to = self._resolve(v_to, other=v_from, func=func)

        if not registry.is_adjacent(SentinelEdge.from_pair(resolved_from, resolved_to)):
            raise RegistryError(
                registry.name,
                f"Cannot register migration with skip versions: {v_from}→{v_to}",
            )

        edge = VersionEdge(
            source=resolved_from,
            target=resolved_to,
            diff=self.adapter.diff(
                resolved_from,
                resolved_to,
                is_backward_compatible=backward_compatible,
            ),
            func=func,
        )
        registry.store_migration(edge)

        return func

    def _resolve(
        self: Self,
        endpoint: Versionable[VersionValue],
        *,
        other: Versionable[VersionValue],
        func: MigrationFunc,
    ) -> Versionable[VersionValue]:
        """Return *endpoint*, reconstructing it when it is not registered.

        A registered endpoint is returned as-is; an unregistered one is
        reconstructed from *other*'s model when ``on_missing`` selects the
        model-reconstruction strategy, else ``ModelNotFoundError``.
        """
        registry = self.registry
        try:
            return registry.get_model(endpoint)
        except ModelNotFoundError:
            pass

        if strategy_for(self.settings.on_missing, adapter=self.adapter) is None:
            raise ModelNotFoundError(registry.name, endpoint.version)

        try:
            anchor = registry.get_model(other)
        except ModelNotFoundError:
            raise ModelNotFoundError(
                registry.name,
                endpoint.version,
            )
        if anchor.model is None:
            raise ModelNotFoundError(
                registry.name,
                endpoint.version,
            )

        outcome = self.reflect(anchor, endpoint, migration=func)
        if outcome.model is not None:
            registry.store_model(outcome.model)
        return registry.get_model(endpoint)

    def reflect(
        self: Self,
        source: Versionable[VersionValue],
        target: Versionable[VersionValue],
        *,
        migration: JsonPatch | MigrationFunc | None = None,
        is_backward_compatible: bool = False,
        strategy: ReconstructionStrategy | None = None,
    ) -> Reconstruction:
        """Uniform reflection: build a diff and materialize the artifact.

        ``migration`` selects the migration-origin path; absent it, the diff is
        computed from the two concrete schemas.  The strategy is selected from
        ``settings.on_missing`` (explicit), else the diff's origin.
        """
        return self._reflection().reflect(
            source,
            target,
            migration=migration,
            is_backward_compatible=is_backward_compatible,
            strategy=strategy,
        )

    def _reflection(self: Self) -> Reflection:
        return Reflection(
            self.adapter,
            self.discovery,
            on_missing=self.settings.on_missing,
        )

    def reconstruct(
        self: Self,
        anchor: Versionable[VersionValue],
        target: Versionable[VersionValue],
        migration: JsonPatch | MigrationFunc,
    ) -> None:
        """Reconstruct and store a missing model for *target*.

        Applies the migration diff to the *anchor* model and stores the result at
        *target*'s version (inverted when the anchor is the newer endpoint).
        """
        outcome = self.reflect(anchor, target, migration=migration)
        if outcome.model is not None:
            self.registry.store_model(outcome.model)

    def propose_migration(
        self: Self,
        source: Versionable[VersionValue],
        target: Versionable[VersionValue],
        *,
        is_backward_compatible: bool = False,
    ) -> JsonPatchMigration:
        """Propose a version-edge migration from two schema versions.

        Diffs the two models' schemas and renders a declarative RFC 6902 spec
        wrapped in a :class:`JsonPatchMigration`. It is a shape-based starting
        point — review it before registering via :meth:`store_migration`. Never
        auto-registers and never touches endpoint models.
        """
        if source.kind != target.kind:
            raise RegistryError(
                self.registry.name,
                f"Cannot propose migration across kinds: "
                f"{source.kind} != {target.kind}",
            )
        if source.strategy != target.strategy:
            raise RegistryError(
                self.registry.name,
                f"Cannot propose migration across strategies: "
                f"{source.strategy.__name__} != {target.strategy.__name__}",
            )
        if source.model is None or target.model is None:
            raise ModelNotFoundError(self.registry.name, source.version)
        outcome = self.reflect(
            source,
            target,
            is_backward_compatible=is_backward_compatible,
            strategy=MigrationReflection(self.adapter),
        )
        assert outcome.migration is not None  # proposal always yields a spec
        return outcome.migration

    def get_migration(
        self: Self,
        key: Transitional[VersionValue],
    ) -> Migratable:
        """Return the registered migration for *key*."""
        return self.registry.get_migration_by_edge(key)

    def remove_migration(
        self: Self,
        key: Transitional[VersionValue],
        *,
        force: bool = False,
    ) -> None:
        """Remove a single migration."""
        edge = self.registry.get_migration_by_edge(key)

        if not force:
            if not self.registry.is_adjacent(key):
                raise RegistryError(
                    self.registry.name,
                    f"Cannot remove migration {key.source}→{key.target}: "
                    "it is not adjacent to any other version.",
                )
            if self.registry.is_critical_edge(key):
                raise RegistryError(
                    self.registry.name,
                    f"Cannot remove critical migration {key.source}→{key.target}. "
                    "It is on the critical path. Use force=True to override.",
                )

        self.registry.remove_migration(SentinelEdge.from_version_edge(edge))

    def remove_migration_range(
        self: Self,
        from_version: Versionable,
        to_version: Versionable,
    ) -> None:
        """Remove all migrations on edges between *from_version* and *to_version*."""
        self.registry.remove_migration_range(from_version, to_version)

    def delete_kind(self: Self, kind: ModelKind) -> None:
        """Remove all models and migrations for *kind*."""
        registry = self.registry

        kind_versions = registry.kind_versions(kind)
        if not kind_versions:
            return

        version_set = set(kind_versions)

        for v in kind_versions:
            for edge in registry.migrations_of(v):
                if edge.source not in version_set or edge.target not in version_set:
                    raise RegistryError(
                        registry.name,
                        f"Cannot delete kind '{kind}': version is referenced "
                        f"by cross-kind migration {edge.source}→{edge.target}",
                    )

        for v in kind_versions:
            for edge in list(registry.migrations_of(v)):
                if edge.source in version_set and edge.target in version_set:
                    if registry.has_hooks(edge):
                        registry.clear_hooks(edge)
                    registry.remove_migration(SentinelEdge.from_version_edge(edge))

        for v in reversed(kind_versions):
            try:
                registry.remove_model(v)
            except RegistryError:
                pass

    def find_migration_path(
        self: Self,
        from_version: Versionable,
        to_version: Versionable,
    ) -> list[tuple[Versionable, Versionable]]:
        """Return a complete migration chain between two versions."""
        return self.registry.migration_path(from_version, to_version)

    def add_hook(
        self: Self,
        key: Transitional[VersionValue],
        hook: Attachable,
    ) -> None:
        """Register a hook for a migration step."""
        edge = self.registry.get_migration_by_edge(key)
        self.registry.add_hook(edge, hook)

    def remove_hook(
        self: Self,
        key: Transitional[VersionValue],
        hook: Attachable | None = None,
    ) -> None:
        """Remove hooks for a migration step."""
        edge = self.registry.get_migration_by_edge(key)
        self.registry.remove_hook(edge, hook)

    def clear_hooks(
        self: Self,
        key: Transitional[VersionValue] | None = None,
    ) -> None:
        """Clear hooks from the registry."""
        if key is None:
            self.registry.clear_hooks()
        else:
            edge = self.registry.get_migration_by_edge(key)
            self.registry.clear_hooks(edge)

    def migrate(
        self: Self,
        data: ModelData,
        target: TargetResolver,
        *,
        container: ModelHandle | None = None,
        version_property: str | None = None,
        depth_limit: int | None = None,
        direction: MigrationDirectionStrategy | None = None,
        on_direction_violation: DirectionViolationStrategy | None = None,
        on_version_not_found: VersionMissingStrategy | None = None,
        executor: Executor[VersionValue] | None = None,
        entry_migration: MigrationEntry[VersionValue] | None = None,
    ) -> ModelData:
        """Converge every versioned entry in *data* to match the target.

        *target* must be a callable ``(current) -> Versionable | None``.
        """
        effective_direction = direction or self.settings.direction
        effective_on_direction_violation = (
            on_direction_violation or self.settings.on_direction_violation
        )
        effective_on_missing = on_version_not_found or self.settings.on_missing_path
        vp = version_property or self.settings.version_property

        plan = self.graph_builder.build(
            data,
            container=container,
            target_resolver=target,
            max_depth=depth_limit,
        )

        active_executor = executor or self.default_executor
        active_entry_migration = entry_migration or self.entry_migration

        return active_executor.run(
            plan,
            registry=self.registry,
            entry_migration=active_entry_migration,
            adapter=self.adapter,
            version_property=vp,
            direction=effective_direction,
            on_direction_violation=effective_on_direction_violation,
            on_missing_path=effective_on_missing,
        )
