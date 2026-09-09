"""Migrations manager."""

import bisect
from typing import Any, Generic, Self, cast, overload

from pyverge.adapters.json_patch import JsonPatch
from pyverge.core.exceptions import (
    MigrationError,
    MigrationNotFoundError,
    ModelNotFoundError,
    RegistryError,
)
from pyverge.core.settings import MigrationSettings
from pyverge.core.types import (
    Attachable,
    Comparable,
    DirectionViolationStrategy,
    Executor,
    Migratable,
    MigrationDirectionStrategy,
    MigrationFunc,
    ModelAdapter,
    ModelBase,
    ModelData,
    ModelKind,
    TargetResolver,
    Transitional,
    Versionable,
    VersionMissingStrategy,
    VersionPair,
    VersionValue,
)
from pyverge.core.versioning import SentinelEdge, SentinelNode, VersionEdge
from pyverge.reflection.discovery import CompositeDiffDiscovery, DiffDiscovery

from .graph import GraphBuilder
from .registry import Registry
from .strategy import DefaultEntryMigration, EntryMigration


class Engine(Generic[VersionValue]):
    """Convergent migration driven by an inferred dependency graph.

    Unlike sequential script migration (Alembic), this engine treats the
    compound ``(kind, version)`` as the first-class axis.  It scans a
    payload for versioned sub-entries using a :attr:`version_property`
    predicate, builds a dependency graph from the migration functions
    that touch each entry, then converges every entry independently
    — forward or backward — to a policy-defined target version.

    Nested entries at different versions (e.g., ``AddressV3`` inside
    ``PersonV1``) are handled naturally: each converges on its own
    terms.  The dependency graph ensures a migration function never
    sees stale children, while avoiding wasted work on subtrees that
    a parent migration will restructure entirely.

    A container model is **not required** — discovery uses the
    ``version_property`` predicate alone.  A typed container provides
    an optional speedup via precomputed shape metrics to prune
    branches.
    """

    def __init__(
        self: Self,
        registry: Registry[VersionValue, ModelBase],
        settings: MigrationSettings,
        default_executor: Executor,
        graph_builder: GraphBuilder[VersionValue],
        adapter: ModelAdapter,
        entry_migration: EntryMigration[VersionValue] | None = None,
    ) -> None:
        """Initialize the engine.

        Args:
            registry: Registry instance.
            settings: Migration configuration.
            executor: Executor used to run the migration graph.
            graph_builder: Pre-configured graph builder (carries its own walker).
            adapter: Provider-specific model adapter used to validate and serialize
                target models.
            entry_migration: Optional per-entry migration strategy. Defaults to
                :class:`DefaultEntryMigration`.
        """
        self.registry = registry
        self.settings = settings
        self.graph_builder = graph_builder
        self.default_executor = default_executor
        self.adapter = adapter
        self.entry_migration = entry_migration or DefaultEntryMigration()
        self.discovery: DiffDiscovery[VersionValue, JsonPatch | MigrationFunc] = (
            CompositeDiffDiscovery()
        )

    def _resolve_model_key(
        self: Self,
        key: Any,
    ) -> SentinelNode[VersionValue]:
        """Normalize a model key to the registry's strict sentinel form."""
        if isinstance(key, tuple):
            kind, value = key
            return SentinelNode[VersionValue](kind, value)
        if isinstance(key, SentinelNode):
            return cast(SentinelNode[VersionValue], key)
        if isinstance(key, type) and issubclass(key, ModelBase):
            versionable = self.registry.get_model_by_class(key)
            return SentinelNode[VersionValue](versionable.kind, versionable.version[1])
        return SentinelNode[VersionValue](key.kind, key.version[1])

    def __contains__(self, index: Any) -> bool:
        """Check membership of a model version or migration edge."""
        if isinstance(index, slice):
            try:
                from_v = self.get_model(self._resolve_model_key(index.start))
                to_v = self.get_model(self._resolve_model_key(index.stop))
                self.find_migration_path(from_v, to_v)
                return True
            except (MigrationError, ModelNotFoundError, RegistryError, TypeError):
                return False

        return self._contains_migration(index) or self._contains_model_key(index)

    def _contains_migration(self, index: Any) -> bool:
        """Check membership of a single migration edge key."""
        try:
            edge_key = (
                index
                if isinstance(index, SentinelEdge)
                else SentinelEdge.from_pair(*index)
            )
            return self.registry.has_migration(edge_key)
        except (
            MigrationNotFoundError,
            ModelNotFoundError,
            RegistryError,
            TypeError,
            AttributeError,
        ):
            return False

    def _contains_model_key(self, index: Any) -> bool:
        """Check membership of a single model key."""
        try:
            resolved = self._resolve_model_key(index)
            return self.registry.get_model(resolved) is not None
        except (ModelNotFoundError, TypeError):
            return False

    @overload
    def __getitem__(self, index: slice) -> list[Migratable]: ...

    @overload
    def __getitem__(self, index: SentinelEdge | tuple) -> Migratable: ...

    def __getitem__(self, index: Any) -> Migratable | list[Migratable]:
        """Select a migration or a path of migrations."""
        if isinstance(index, slice):
            from_v = self.get_model(self._resolve_model_key(index.start))
            to_v = self.get_model(self._resolve_model_key(index.stop))
            path = self.find_migration_path(from_v, to_v)
            return [
                self.registry.get_migration_by_edge(SentinelEdge.from_pair(src, dst))
                for src, dst in path
            ]

        if isinstance(index, (SentinelEdge, tuple)):
            edge_key = (
                index
                if isinstance(index, SentinelEdge)
                else SentinelEdge.from_pair(*index)
            )
            return self.registry.get_migration_by_edge(edge_key)

        raise RegistryError(
            self.registry.name, f"Unsupported index type: {type(index)}"
        )

    def store_model(
        self: Self,
        version: Versionable[VersionValue, ModelBase],
    ) -> Versionable[VersionValue, ModelBase]:
        """Register a model version in the registry."""
        return self.registry.store_model(version)

    def get_model(
        self: Self,
        key: Comparable[VersionValue],
    ) -> Versionable[VersionValue, ModelBase]:
        """Return the model matching *key*."""
        return self.registry.get_model(key)

    def get_model_by_class(
        self: Self,
        cls: type[ModelBase],
    ) -> Versionable[VersionValue, ModelBase]:
        """Return the model matching the Pydantic class *cls*."""
        return self.registry.get_model_by_class(cls)

    def remove_model(
        self: Self,
        key: Comparable[VersionValue],
    ) -> None:
        """Remove a model version from the registry."""
        self.registry.remove_model(key)

    def model_latest(
        self: Self,
        kind: ModelKind,
    ) -> Versionable[VersionValue, ModelBase]:
        """Most recent version for *kind*."""
        return self.registry.latest(kind)

    def find_model(
        self: Self,
        key: Comparable[VersionValue] | ModelKind,
    ) -> Versionable[VersionValue, ModelBase]:
        """Return the model matching *key*."""
        if isinstance(key, str):
            return self.registry.latest(key)
        return self.get_model(key)

    def store_migration(
        self: Self,
        key: VersionPair[VersionValue, ModelBase],
        func: MigrationFunc,
        *,
        backward_compatible: bool = False,
    ) -> MigrationFunc:
        """Register a migration with adjacency and backward-compat validation.

        Endpoints without a concrete model are reconstructed from the other
        endpoint's model when ``settings.on_missing_model == "reconstruct"``;
        otherwise ``ModelNotFoundError`` is raised.  The migration edge is
        stored only after both endpoints have models.
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
        endpoint: Versionable[VersionValue, ModelBase],
        *,
        other: Versionable[VersionValue, ModelBase],
        func: MigrationFunc,
    ) -> Versionable[VersionValue, ModelBase]:
        """Return *endpoint*, reconstructing it when it is not registered.

        A registered endpoint (including a registered meta node) is returned
        as-is.  An unregistered endpoint is reconstructed from *other*'s model
        when ``settings.on_missing_model == "reconstruct"``; otherwise
        ``ModelNotFoundError`` is raised.
        """
        registry = self.registry
        try:
            return registry.get_model(endpoint)
        except ModelNotFoundError:
            pass

        if self.settings.on_missing_model != "reconstruct":
            raise ModelNotFoundError(
                registry.name,
                f"Cannot register migration: endpoint {endpoint} is not registered "
                "and on_missing_model is not 'reconstruct'",
            )
        if other.model is None:
            raise ModelNotFoundError(
                registry.name,
                f"Cannot reconstruct {endpoint}: neither endpoint has a model",
            )

        self.reconstruct(other, endpoint, func)
        return registry.get_model(endpoint)

    def reconstruct(
        self: Self,
        anchor: Versionable[VersionValue, ModelBase],
        target: Versionable[VersionValue, ModelBase],
        migration: JsonPatch | MigrationFunc,
    ) -> None:
        """Reconstruct and store a missing model for *target*.

        Applies the migration's diff to the *anchor* model via the provider
        adapter and stores the resulting model at *target*'s version.  The
        diff is applied forward when the anchor predates the target and
        inverted when it is the newer endpoint.
        """
        diff = self.discovery.discover(migration, anchor, target)
        if anchor.version > target.version:
            diff = diff.inverted()
        model = self.adapter.materialize(anchor.model, diff, target.version[1])
        self.registry.store_model(self.adapter.versionable(model))

    def get_migration(
        self: Self,
        key: Transitional[VersionValue, ModelBase, ModelBase],
    ) -> Migratable:
        """Return the registered migration for *key*."""
        return self.registry.get_migration_by_edge(key)

    def remove_migration(
        self: Self,
        key: Transitional[VersionValue, ModelBase, ModelBase],
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
        registry = self.registry

        if from_version.version[0] != to_version.version[0]:
            raise RegistryError(
                registry.name,
                f"Cannot remove range across kinds: "
                f"{from_version.version[0]} != {to_version.version[0]}",
            )

        kind_versions = registry.kind_versions(from_version.version[0])
        lo = bisect.bisect_left(kind_versions, from_version)
        hi = bisect.bisect_left(kind_versions, to_version)

        keys_to_remove: list[SentinelEdge] = []
        for i in range(lo, hi):
            edge_key = SentinelEdge.from_pair(kind_versions[i], kind_versions[i + 1])
            if not self.registry.has_migration(edge_key):
                continue
            if self.registry.is_adjacent(edge_key):
                msg = (
                    f"Cannot remove critical migration {edge_key.source}→"
                    f"{edge_key.target} in range. Remove it individually with "
                    "force=True or remove hooks first."
                )
                raise RegistryError(registry.name, msg)
            if registry.has_hooks(edge_key):
                raise RegistryError(
                    registry.name,
                    f"Cannot remove migration {edge_key.source}→{edge_key.target}. "
                    "Remove hooks first.",
                )
            keys_to_remove.append(edge_key)

        for edge_key in keys_to_remove:
            registry.remove_migration(edge_key)

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
        registry = self.registry

        if from_version.kind != to_version.kind:
            raise RegistryError(
                registry.name,
                f"Cannot find path across kinds: "
                f"{from_version.kind} != {to_version.kind}",
            )

        kind_versions = registry.kind_versions(from_version.kind)

        if from_version not in kind_versions:
            raise MigrationError(
                registry.name,
                from_version,
                to_version,
                f"Version {from_version} is not registered",
            )
        if to_version not in kind_versions:
            raise MigrationError(
                registry.name,
                (from_version, to_version),
            )

        lo = kind_versions.index(from_version)
        hi = kind_versions.index(to_version)
        if lo == hi:
            return []

        step = 1 if lo < hi else -1
        path: list[tuple[Versionable, Versionable]] = []
        current = from_version
        while lo != hi:
            nxt = kind_versions[lo + step]
            edge_key = SentinelEdge.from_pair(current, nxt)
            if registry.has_migration(edge_key):
                path.append((current, nxt))
                current = nxt
                lo += step
            else:
                raise MigrationError(
                    registry.name,
                    current,
                    nxt,
                    f"No migration key is found ({current}, {nxt})",
                )
        return path

    def add_hook(
        self: Self,
        key: Transitional[VersionValue, ModelBase, ModelBase],
        hook: Attachable,
    ) -> None:
        """Register a hook for a migration step."""
        edge = self.registry.get_migration_by_edge(key)
        self.registry.add_hook(edge, hook)

    def remove_hook(
        self: Self,
        key: Transitional[VersionValue, ModelBase, ModelBase],
        hook: Attachable | None = None,
    ) -> None:
        """Remove hooks for a migration step."""
        edge = self.registry.get_migration_by_edge(key)
        self.registry.remove_hook(edge, hook)

    def clear_hooks(
        self: Self,
        key: Transitional[VersionValue, ModelBase, ModelBase] | None = None,
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
        container: type[ModelBase] | None = None,
        version_property: str | None = None,
        depth_limit: int | None = None,
        direction: MigrationDirectionStrategy | None = None,
        on_direction_violation: DirectionViolationStrategy | None = None,
        on_version_not_found: VersionMissingStrategy | None = None,
        executor: Executor | None = None,
        entry_migration: EntryMigration[VersionValue] | None = None,
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

        graph = self.graph_builder.build(
            data,
            container=container,
            target_resolver=target,
            max_depth=depth_limit,
        )

        active_executor = executor or self.default_executor
        active_entry_migration = entry_migration or self.entry_migration

        return active_executor.run(
            data,
            graph,
            registry=self.registry,
            entry_migration=active_entry_migration,
            adapter=self.adapter,
            version_property=vp,
            direction=effective_direction,
            on_direction_violation=effective_on_direction_violation,
            on_missing_path=effective_on_missing,
        )
