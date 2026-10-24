from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Generic, Self, cast, overload

from pyverge.convergence.catalog import (
    GraphCatalog,
    Registry,
)
from pyverge.convergence.errors import (
    BackwardCompatibilityError,
    CatalogError,
    MigrationNotFoundError,
    MissingReferenceError,
    ModelNotFoundError,
)
from pyverge.core.types import (
    Attachable,
    MigrationFunc,
    ModelHandle,
    ModelKind,
    VersionValue,
)
from pyverge.migrations.identity import MigrationIdentityResolver
from pyverge.migrations.json_patch import JsonPatch
from pyverge.reflection.ports import DiffProvider
from pyverge.schemas.types import (
    ModelAdapter,
)
from pyverge.versioning import (
    Comparable,
    CompatibilityReport,
    DiffMaterializer,
    EdgeKey,
    Migratable,
    Transitional,
    Versionable,
    VersionEdge,
    VersionNode,
    VersionPair,
)


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
        adapter: ModelAdapter,
        identity_resolver: MigrationIdentityResolver,
        materializers: Mapping[str, DiffMaterializer[Any]],
        diff_provider: DiffProvider[VersionValue],
        on_missing: str = "raise",
    ) -> None:
        self.registry = registry
        self.adapter = adapter
        self.identity_resolver = identity_resolver
        self.materializers = materializers
        self.diff_provider = diff_provider
        self.on_missing = on_missing

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
        return cast("GraphCatalog", self.registry.snapshot())

    def lock(self) -> GraphCatalog:
        """Freeze this build registry and return the runtime snapshot."""
        return cast("GraphCatalog", self.registry.lock())

    def __contains__(self, index: Any) -> bool:
        """Check membership of a typed model version or migration edge.

        Typed only: fluent keys (raw tuples, bare model classes) and slices are
        sugar the manager owns.
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
        """Select a typed model version or migration."""
        return self.registry[index]

    def store_model(
        self: Self,
        version: VersionNode[VersionValue],
    ) -> VersionNode[VersionValue]:
        """Register a model version via the strict store.

        A duplicate ``(kind, version)`` fails loudly — re-registration is a
        caller error.  Use :meth:`reconcile_model` for an idempotent fallback.
        """
        return self.registry.store_model(version)

    def reconcile_model(
        self: Self,
        version: VersionNode[VersionValue],
    ) -> VersionNode[VersionValue]:
        """Register a model version, treating an identical re-registration as a
        no-op and raising :class:`ModelConflictError` on a differing surface.
        """
        return self.registry.reconcile_model(version)

    def validate(
        self: Self,
        key: Comparable[VersionValue] | None = None,
    ) -> None:
        """Validate that registered models' declared references are registered.

        With *version*, only that node is checked; otherwise the whole registry.
        Raises :class:`MissingReferenceError` naming the absent references.
        """
        nodes = (
            [self.registry.get_model(key)]
            if key is not None
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
    ) -> VersionNode[VersionValue]:
        """Return the model matching *key*."""
        return self.registry.get_model(key)

    def get_model_by_class(
        self: Self,
        cls: ModelHandle,
    ) -> VersionNode[VersionValue]:
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
    ) -> VersionNode[VersionValue]:
        """Most recent version for *kind*."""
        return self.registry.latest(kind)

    def get_earliest_model(
        self: Self,
        kind: ModelKind,
    ) -> VersionNode[VersionValue]:
        """Earliest version for *kind*."""
        return self.registry.earliest(kind)

    def get_entities(self: Self) -> list[ModelKind]:
        """Kinds that have at least one registered version."""
        return self.registry.entities

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

        diff = self.adapter.diff(resolved_from, resolved_to)
        if backward_compatible:
            report = CompatibilityReport.from_diff(
                diff,
                identity_fields=frozenset(
                    {self.adapter.kind_property, self.adapter.version_property}
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

        edge = VersionEdge(
            source=resolved_from,
            target=resolved_to,
            diff=diff,
            func=func,
            migration=self.identity_resolver.resolve(func),
        )
        registry.store_migration(edge)

        return func

    def _resolve(
        self: Self,
        endpoint: Comparable[VersionValue],
        *,
        other: Comparable[VersionValue],
        func: MigrationFunc,
    ) -> VersionNode[VersionValue]:
        """Return *endpoint*, reconstructing it when it is not registered.

        A registered endpoint is returned as-is; an unregistered one is
        reconstructed from *other*'s model when a model materializer is
        configured, else ``ModelNotFoundError``.
        """
        registry = self.registry
        try:
            return registry.get_model(endpoint)
        except ModelNotFoundError:
            pass

        if (
            self.on_missing != "reconstruct_model"
            or "reconstruct_model" not in self.materializers
        ):
            raise ModelNotFoundError(registry.name, endpoint.version)

        try:
            anchor = registry.get_model(other)
        except ModelNotFoundError:
            raise ModelNotFoundError(
                registry.name,
                endpoint.version,
            )
        return self._materialize_missing(anchor, endpoint, func)

    def _materialize_missing(
        self: Self,
        anchor: VersionNode[VersionValue],
        target: Comparable[VersionValue],
        func: MigrationFunc,
    ) -> VersionNode[VersionValue]:
        """Materialize *target* from *anchor* and store the result."""
        diff = self._reflection().diff(anchor, target, migration=func)
        node = self.materializers["reconstruct_model"].materialize(diff)
        if not isinstance(node, VersionNode):
            raise ModelNotFoundError(self.registry.name, target.version)
        self.registry.store_model(node)
        return node

    def _reflection(self: Self) -> DiffProvider[VersionValue]:
        return self.diff_provider

    def reconstruct(
        self: Self,
        anchor: VersionNode[VersionValue],
        target: Comparable[VersionValue],
        migration: JsonPatch | MigrationFunc,
    ) -> None:
        """Reconstruct and store a missing model for *target*.

        Applies the migration diff to the *anchor* model and stores the result at
        *target*'s version (inverted when the anchor is the newer endpoint).
        """
        self._materialize_missing(anchor, target, migration)

    def propose_migration(
        self: Self,
        source: VersionNode[VersionValue],
        target: VersionNode[VersionValue],
    ) -> Any:
        """Propose a version-edge migration from two schema versions.

        Diffs the two models' schemas and renders a declarative RFC 6902 spec
        wrapped in a :class:`JsonPatchMigration`. It is a shape-based starting
        point — review it before registering via :meth:`store_migration`. Never
        auto-registers and never touches endpoint models.
        """
        if source.kind != target.kind:
            raise CatalogError(
                self.registry.name,
                f"Cannot propose migration across kinds: "
                f"{source.kind} != {target.kind}",
            )
        if source.strategy != target.strategy:
            raise CatalogError(
                self.registry.name,
                f"Cannot propose migration across strategies: "
                f"{source.strategy.__name__} != {target.strategy.__name__}",
            )
        diff = self._reflection().diff(source, target)
        return self.materializers["reconstruct_migration"].materialize(diff)

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
                    raise CatalogError(
                        registry.name,
                        f"Cannot delete kind '{kind}': version is referenced "
                        f"by cross-kind migration {edge.source}→{edge.target}",
                    )

        for v in kind_versions:
            for edge in list(registry.migrations_of(v)):
                if edge.source in version_set and edge.target in version_set:
                    if registry.has_hooks(edge):
                        registry.clear_hooks(edge)
                    registry.remove_migration(EdgeKey.from_version_edge(edge))

        for v in reversed(kind_versions):
            try:
                registry.remove_model(v)
            except CatalogError:
                pass

    def find_migration_path(
        self: Self,
        from_version: Versionable,
        to_version: Versionable,
    ) -> list[tuple[VersionNode[VersionValue], VersionNode[VersionValue]]]:
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
