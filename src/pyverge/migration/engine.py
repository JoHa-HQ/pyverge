import bisect
from typing import Any, Generic, Self, cast, overload

from pyverge.core.exceptions import (
    MigrationError,
    MigrationNotFoundError,
    MissingReferenceError,
    ModelConflictError,
    ModelNotFoundError,
    RegistryError,
)
from pyverge.core.render import JsonPatchRender
from pyverge.core.settings import MigrationSettings
from pyverge.core.versioning import SentinelEdge, VersionEdge, VersionNode
from pyverge.ports.json_patch import JsonPatch
from pyverge.ports.json_patch.migration import JsonPatchMigration
from pyverge.reflection.discovery import CompositeDiffDiscovery, DiffDiscovery
from pyverge.types import (
    Attachable,
    Comparable,
    DirectionViolationStrategy,
    Executor,
    Migratable,
    MigrationDirectionStrategy,
    MigrationEntry,
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
        registry: Registry[VersionValue, ModelBase],
        settings: MigrationSettings,
        default_executor: Executor,
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

    def _resolve_model_key(
        self: Self,
        key: Any,
    ) -> VersionNode[VersionValue, ModelBase]:
        """Normalize a model key to a version node form."""
        if isinstance(key, tuple):
            kind, value = key
            return VersionNode[VersionValue, ModelBase](
                _model=None, _value=value, _kind=kind
            )
        if isinstance(key, VersionNode):
            return cast(VersionNode[VersionValue, ModelBase], key)
        if isinstance(key, type) and issubclass(key, ModelBase):
            versionable = self.registry.get_model_by_class(key)
            return VersionNode[VersionValue, ModelBase](
                _model=None,
                _value=versionable.version[1],
                _kind=versionable.kind,
            )
        return VersionNode[VersionValue, ModelBase](
            _model=None, _value=key.version[1], _kind=key.kind
        )

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
        """Register a model version, reconciling against an existing one.

        An identical re-registration (same ``fields`` surface) is a no-op; a
        different surface raises :class:`ModelConflictError`.
        """
        try:
            existing = self.registry.get_model(version)
        except ModelNotFoundError:
            return self.registry.store_model(version)
        if existing.fields != version.fields:
            raise ModelConflictError(
                self.registry.name,
                version.version,
                existing.fields,
                version.fields,
            )
        return existing

    def validate(
        self: Self,
        version: Versionable[VersionValue, ModelBase] | None = None,
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

    def get_latest_model(
        self: Self,
        kind: ModelKind,
    ) -> Versionable[VersionValue, ModelBase]:
        """Most recent version for *kind*."""
        return self.registry.latest(kind)

    def get_earliest_model(
        self: Self,
        kind: ModelKind,
    ) -> Versionable[VersionValue, ModelBase]:
        """Earliest version for *kind*."""
        return self.registry.earliest(kind)

    def store_migration(
        self: Self,
        key: VersionPair[VersionValue, ModelBase],
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
        endpoint: Versionable[VersionValue, ModelBase],
        *,
        other: Versionable[VersionValue, ModelBase],
        func: MigrationFunc,
    ) -> Versionable[VersionValue, ModelBase]:
        """Return *endpoint*, reconstructing it when it is not registered.

        A registered endpoint is returned as-is; an unregistered one is
        reconstructed from *other*'s model when ``on_missing ==
        "reconstruct_model"``, else ``ModelNotFoundError``.
        """
        registry = self.registry
        try:
            return registry.get_model(endpoint)
        except ModelNotFoundError:
            pass

        if self.settings.on_missing != "reconstruct_model":
            raise ModelNotFoundError(
                registry.name,
                endpoint.version,
            )

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

        self.reconstruct(anchor, endpoint, func)
        return registry.get_model(endpoint)

    def reconstruct(
        self: Self,
        anchor: Versionable[VersionValue, ModelBase],
        target: Versionable[VersionValue, ModelBase],
        migration: JsonPatch | MigrationFunc,
    ) -> None:
        """Reconstruct and store a missing model for *target*.

        Applies the migration diff to the *anchor* model and stores the result at
        *target*'s version (inverted when the anchor is the newer endpoint).
        """
        diff = self.discovery.discover(migration, anchor, target)
        if anchor.version > target.version:
            diff = diff.inverted()
        model = self.adapter.materialize(anchor.model, diff, target.version[1])
        self.registry.store_model(self.adapter.versionable(model))

    def propose_migration(
        self: Self,
        source: Versionable[VersionValue, ModelBase],
        target: Versionable[VersionValue, ModelBase],
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
        diff = self.adapter.diff(
            source,
            target,
            is_backward_compatible=is_backward_compatible,
        )
        spec = {
            "from": str(source.version[1]),
            "to": str(target.version[1]),
            "ops": JsonPatchRender(diff)(),
        }
        return JsonPatchMigration(spec)

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
