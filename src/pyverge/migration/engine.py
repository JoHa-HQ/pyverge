"""Migrations manager."""

import bisect
from typing import Any, Generic, Self, cast

from .diff import PydanticDiff
from .exceptions import (
    MigrationError,
    MigrationNotFoundError,
    ModelNotFoundError,
    RegistryError,
)
from .graph import GraphBuilder
from .models import MigrationSettings
from .policy import compile_target_resolver
from .registry import Registry
from .strategy import DefaultEntryMigration, EntryMigration
from .types import (
    Attachable,
    Comparable,
    DirectionViolationStrategy,
    Executor,
    Migratable,
    MigrationDirectionStrategy,
    MigrationFunc,
    MigrationKeyInput,
    ModelAdapter,
    ModelBase,
    ModelData,
    ModelKind,
    ModelVersionKey,
    TargetPolicy,
    TargetResolver,
    Versionable,
    VersionMissingStrategy,
    VersionValue,
)
from .versioning import SentinelEdge, SentinelNode, VersionEdge

# Expected length for an endpoint-pair tuple such as ``(Versionable, Versionable)``.
_MIGRATION_PAIR_LEN: int = 2


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

    def _resolve_model_key(
        self: Self,
        key: Comparable | ModelVersionKey | type[ModelBase],
    ) -> SentinelNode[VersionValue]:
        """Normalize a model key to the registry's strict sentinel form."""
        if isinstance(key, tuple):
            kind, value = cast(ModelVersionKey, key)
            return SentinelNode[VersionValue](kind, value)
        if isinstance(key, SentinelNode):
            return cast(SentinelNode[VersionValue], key)
        if isinstance(key, type) and issubclass(key, ModelBase):
            versionable = self.registry.get_model_by_class(key)
            return SentinelNode[VersionValue](
                versionable.kind, versionable.version[1]
            )
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
        if not self._is_migration_pair(index):
            return False
        try:
            pair = self._resolve_migration_key(index)
            return self.registry.has_migration(SentinelEdge.from_pair(*pair))
        except (MigrationNotFoundError, ModelNotFoundError, RegistryError, TypeError):
            return False

    def _contains_model_key(self, index: Any) -> bool:
        """Check membership of a single model key."""
        try:
            resolved = self._resolve_model_key(index)
            return self.registry.get_model(resolved) is not None
        except (ModelNotFoundError, TypeError):
            return False

    def _is_migration_pair(self, index: Any) -> bool:
        """Return ``True`` when *index* looks like a migration endpoint pair."""
        if isinstance(index, SentinelEdge):
            return True
        return (
            isinstance(index, tuple)
            and len(index) == _MIGRATION_PAIR_LEN
            and not isinstance(index[0], str)
        )

    def __getitem__(self, index: Any) -> MigrationFunc | list[MigrationFunc]:
        """Select a migration function or a path of functions."""
        if isinstance(index, slice):
            from_v = self.get_model(self._resolve_model_key(index.start))
            to_v = self.get_model(self._resolve_model_key(index.stop))
            path = self.find_migration_path(from_v, to_v)
            return [
                self.registry.get_migration_by_edge(
                    SentinelEdge.from_pair(src, dst)
                ).func
                for src, dst in path
            ]

        if self._is_migration_pair(index):
            pair = self._resolve_migration_key(index)
            return self.registry.get_migration_by_edge(
                SentinelEdge.from_pair(*pair)
            ).func

        raise RegistryError(
            self.registry.name, f"Unsupported index type: {type(index)}"
        )

    def _resolve_migration_key(
        self: Self,
        key: MigrationKeyInput,
    ) -> tuple[Versionable, Versionable]:
        """Normalize a migration key to a strict ``Versionable`` pair."""
        from_ref, to_ref = key
        return self.get_model(from_ref), self.get_model(to_ref)

    def _resolve_edge(
        self: Self,
        key: MigrationKeyInput,
    ) -> tuple[tuple[Versionable, Versionable], Migratable]:
        """Normalize *key* and fetch the registered edge."""
        pair = self._resolve_migration_key(key)
        return pair, self.registry.get_migration_by_edge(SentinelEdge.from_pair(*pair))

    def store_model(
        self: Self,
        version: Versionable[VersionValue, ModelBase],
    ) -> Versionable:
        """Register a model version in the registry."""
        return self.registry.store_model(version)

    def get_model(
        self: Self,
        key: Comparable | ModelVersionKey | type[ModelBase],
    ) -> Versionable:
        """Return the model matching *key*."""
        return self.registry.get_model(self._resolve_model_key(key))

    def remove_model(
        self: Self,
        key: Comparable | ModelVersionKey | type[ModelBase],
    ) -> None:
        """Remove a model version from the registry."""
        if isinstance(key, tuple):
            kind, value = cast(ModelVersionKey, key)
            sentinel = SentinelNode[VersionValue](kind, value)
        elif isinstance(key, type) and issubclass(key, ModelBase):
            sentinel = self.registry.get_model_by_class(key)
        else:
            sentinel = key
        self.registry.remove_model(sentinel)

    def model_latest(
        self: Self,
        kind: ModelKind,
    ) -> Versionable[VersionValue, ModelBase]:
        """Most recent version for *kind*."""
        return self.registry.latest(kind)

    def find_model(
        self: Self,
        key: ModelVersionKey | type[ModelBase] | ModelKind,
    ) -> Versionable | None:
        """Return the model matching *key*, or ``None`` if not found."""
        try:
            if isinstance(key, str):
                return self.registry.latest(key)
            return self.get_model(key)
        except (ModelNotFoundError, RegistryError, ValueError):
            return None

    def store_migration(
        self: Self,
        key: MigrationKeyInput,
        func: MigrationFunc,
        *,
        backward_compatible: bool = False,
    ) -> MigrationFunc:
        """Register a migration with adjacency and backward-compat validation."""
        registry = self.registry
        v_from, v_to = self._resolve_migration_key(key)

        if v_from.kind != v_to.kind:
            raise RegistryError(
                registry.name,
                f"Cannot register migration across kinds: {v_from.kind} != {v_to.kind}",
            )

        versions = registry.kind_versions(v_from.kind)
        lo = bisect.bisect_left(versions, v_from)
        hi = bisect.bisect_left(versions, v_to)
        lo, hi = sorted((lo, hi))

        if hi - lo > 1:
            gap = [
                SentinelEdge.from_pair(versions[i], versions[i + 1])
                for i in range(lo, hi)
            ]
            for gap_edge in gap:
                try:
                    edge = registry.get_migration_by_edge(gap_edge)
                except MigrationNotFoundError as exc:
                    raise RegistryError(
                        registry.name,
                        f"Migration edge {v_from}→{v_to} is not adjacent "
                        "and consecutive edges inside the gap are not all "
                        "registered and backward-compatible",
                    ) from exc
                if not edge.diff.is_backward_compatible:
                    raise RegistryError(
                        registry.name,
                        f"Migration edge {v_from}→{v_to} is not adjacent "
                        "and consecutive edges inside the gap are not all "
                        "backward-compatible",
                    )

        edge = VersionEdge(
            diff=PydanticDiff.from_pair(
                source=v_from,
                target=v_to,
                is_backward_compatible=backward_compatible,
            ),
            func=func,
        )
        registry.store_migration(edge)
        return func

    def get_migration(
        self: Self,
        key: MigrationKeyInput,
    ) -> MigrationFunc:
        """Return the migration function for *key*."""
        _, edge = self._resolve_edge(key)
        return edge.func

    def remove_migration(
        self: Self,
        key: MigrationKeyInput,
        *,
        force: bool = False,
    ) -> None:
        """Remove a single migration."""
        pair, edge = self._resolve_edge(key)

        if not force and self.registry.is_adjacent(SentinelEdge.from_pair(*pair)):
            raise RegistryError(
                self.registry.name,
                f"Cannot remove critical migration {pair[0]}→{pair[1]}. "
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
        key: MigrationKeyInput,
        hook: Attachable,
    ) -> None:
        """Register a hook for a migration step."""
        _, edge = self._resolve_edge(key)
        self.registry.add_hook(edge, hook)

    def remove_hook(
        self: Self,
        key: MigrationKeyInput,
        hook: Attachable | None = None,
    ) -> None:
        """Remove hooks for a migration step."""
        _, edge = self._resolve_edge(key)
        self.registry.remove_hook(edge, hook)

    def clear_hooks(
        self: Self,
        key: MigrationKeyInput | None = None,
    ) -> None:
        """Clear hooks from the registry."""
        if key is None:
            self.registry.clear_hooks()
        else:
            _, edge = self._resolve_edge(key)
            self.registry.clear_hooks(edge)

    def migrate(
        self: Self,
        data: ModelData,
        target: TargetPolicy | None = None,
        *,
        target_resolver: TargetResolver | None = None,
        container: type[ModelBase] | None = None,
        version_property: str | None = None,
        depth_limit: int | None = None,
        direction: MigrationDirectionStrategy | None = None,
        on_direction_violation: DirectionViolationStrategy | None = None,
        on_version_not_found: VersionMissingStrategy | None = None,
        executor: Executor | None = None,
        entry_migration: EntryMigration[VersionValue] | None = None,
    ) -> ModelData:
        """Converge every versioned entry in *data* to match the policy."""
        effective_direction = direction or self.settings.direction
        effective_on_direction_violation = (
            on_direction_violation or self.settings.on_direction_violation
        )
        effective_on_missing = on_version_not_found or self.settings.on_missing_path
        vp = version_property or self.settings.version_property

        if target_resolver is None:
            target_resolver = compile_target_resolver(
                self.registry,
                target or self.settings.target_strategy,
                version_property=vp,
                adapter=self.adapter,
            )

        graph = self.graph_builder.build(
            data,
            container=container,
            target_resolver=target_resolver,
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
