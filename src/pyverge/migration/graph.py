"""Dependency graph for convergent migration.

:class:`GraphBuilder` scans a payload for versioned dicts and builds a
structural containment :class:`MigrationGraph`.  The graph captures which
entries exist and how they nest — children converge before parents.

A versioned entity is identified by a strict ``(kind, version)`` predicate:
the dict must contain the configured ``kind_property`` and ``version_property``,
and the pair must be registered.  Everything else is traversed but not treated
as a migratable entry.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic

from pydantic import BaseModel

from .exceptions import MaxDepthExceededError, RegistryError
from .models import DiscoverySettings
from .registry import Registry
from .types import (
    Attachable,
    ModelKind,
    TargetResolver,
    Versionable,
    VersionValue,
    VModel,
    Walker,
)
from .versioning import SentinelEdge


@dataclass(frozen=True, slots=True)
class GraphEntry(Generic[VersionValue, VModel]):
    """A single versioned entry discovered in a payload.

    Attributes:
        path: Position in the payload (``("document", "address")``).
        source: Current registered version found in the payload.
        target: Version to converge this entry to (resolved by the caller).
        steps: Resolved migration path as a sequence of ``(source, target)``
            pairs for each step.
        hooks: Sequence of hooks for each migration step in this entry's path.
        target_model: Optional Pydantic model class to validate the migrated
            entry against.
    """

    path: tuple[str | int, ...]
    source: Versionable[VersionValue, VModel]
    target: Versionable[VersionValue, VModel]
    steps: tuple[
        tuple[Versionable[VersionValue, VModel], Versionable[VersionValue, VModel]], ...
    ] = ()
    hooks: tuple[tuple[Attachable, ...], ...] = ()
    target_model: type[VModel] | None = None

    @property
    def kind(self) -> ModelKind:
        return self.source.kind

    def __repr__(self) -> str:
        return (
            f"GraphEntry(path={self.path!r}, "
            f"source={self.source!s}, target={self.target!s})"
        )


class MigrationGraph(Generic[VersionValue]):
    """Structural containment DAG of versioned entries.

    Built by :class:`GraphBuilder` from a payload.  The graph is consumed by
    the engine to determine migration order and parallelization groups.
    """

    def __init__(self, entries: list[GraphEntry[VersionValue, BaseModel]]) -> None:
        self._entries = entries
        self._by_path: dict[
            tuple[str | int, ...], GraphEntry[VersionValue, BaseModel]
        ] = {e.path: e for e in entries}

    @property
    def entries(self) -> list[GraphEntry[VersionValue, BaseModel]]:
        """All discovered versioned entries (build order)."""
        return list(self._entries)

    def topological_order(self) -> list[GraphEntry[VersionValue, BaseModel]]:
        """Return entries in valid migration order: children before parents.

        Structural containment means a child's path is always a strict
        extension of its parent's.  Sorting by path length descending
        guarantees children precede their parents.  Equal-length paths
        are ordered lexicographically for determinism.
        """
        return sorted(
            self._entries,
            key=lambda e: (-len(e.path), e.path),
        )

    def execution_levels(self) -> list[list[GraphEntry[VersionValue, BaseModel]]]:
        """Return entries grouped by execution wave: leaves first, roots last.

        All leaf entries (entries with no registered children) run in the
        first wave.  After a wave finishes, any entry whose children all
        appeared in previous waves becomes a leaf and joins the next wave.
        Entries within the same wave are independent and can be migrated in
        parallel.
        """
        if not self._entries:
            return []

        entries_by_path = self._by_path
        children: dict[tuple[str | int, ...], list[tuple[str | int, ...]]] = {
            e.path: [] for e in self._entries
        }
        pending: dict[tuple[str | int, ...], int] = {e.path: 0 for e in self._entries}

        for entry in self._entries:
            parent_path = self._parent_path(entry.path)
            if parent_path is not None:
                children[parent_path].append(entry.path)
                pending[parent_path] += 1

        current: list[GraphEntry[VersionValue, BaseModel]] = [
            entries_by_path[p] for p, count in pending.items() if count == 0
        ]
        levels: list[list[GraphEntry[VersionValue, BaseModel]]] = []

        while current:
            current.sort(key=lambda e: e.path)
            levels.append(current)
            next_wave: list[GraphEntry[VersionValue, BaseModel]] = []
            for entry in current:
                parent_path = self._parent_path(entry.path)
                if parent_path is None:
                    continue
                pending[parent_path] -= 1
                if pending[parent_path] == 0:
                    next_wave.append(entries_by_path[parent_path])
            current = next_wave

        return levels

    def _parent_path(self, path: tuple[str | int, ...]) -> tuple[str | int, ...] | None:
        """Return the longest registered proper prefix of *path*, or ``None``."""
        prefix: tuple[str | int, ...] = ()
        parent: tuple[str | int, ...] | None = None
        for step in path[:-1]:
            prefix += (step,)
            if prefix in self._by_path:
                parent = prefix
        return parent

    def independent_roots(self) -> list[GraphEntry[VersionValue, BaseModel]]:
        """Return root entries of each disjoint connected component.

        An entry is a root if no other entry's path is a proper prefix.
        Roots can be migrated in parallel once their children are done.
        """
        all_paths = {e.path for e in self._entries}
        roots: list[GraphEntry[VersionValue, BaseModel]] = []
        for entry in self._entries:
            prefix: tuple[str | int, ...] = ()
            is_root = True
            for step in entry.path[:-1]:
                prefix += (step,)
                if prefix in all_paths:
                    is_root = False
                    break
            if is_root:
                roots.append(entry)
        return roots

    def entry_at(
        self, path: tuple[str | int, ...]
    ) -> GraphEntry[VersionValue, BaseModel] | None:
        """Return the entry at *path*, or ``None``."""
        return self._by_path.get(path)

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)

    def __repr__(self) -> str:
        return f"MigrationGraph(entries={len(self._entries)})"


class GraphBuilder(Generic[VersionValue]):
    """Builds a :class:`MigrationGraph` by scanning a payload for versioned dicts.

    The builder delegates the actual traversal to a :class:`Walker`.  When no
    container is supplied it uses the containerless :class:`CompoundKeyWalker`;
    when a container model is supplied it uses the schema-driven
    :class:`PydanticWalker`.
    """

    def __init__(
        self,
        registry: Registry[VersionValue],
        settings: DiscoverySettings,
        walker: Walker,
    ) -> None:
        self._registry = registry
        self._settings = settings
        self._walker = walker

    @property
    def walker(self) -> Walker:
        """The configured payload walker."""
        return self._walker

    def build(
        self,
        data: dict[str, Any],
        *,
        target_resolver: TargetResolver,
        container: type[BaseModel] | None = None,
        max_depth: int | None = None,
    ) -> MigrationGraph[VersionValue]:
        """Scan *data* and return a migration graph of versioned entries.

        Args:
            container: Optional Pydantic schema model that drives discovery.
                The configured walker must support the container (e.g.
                :class:`PydanticWalker`).
            max_depth: Override the configured ``max_migration_depth`` for
                this call. ``0`` = top-level only, ``-1`` = unlimited.
        """
        active_walker = self._walker
        default_depth = self._settings.max_migration_depth
        limit = default_depth if max_depth is None else max_depth
        entries: list[GraphEntry[VersionValue, BaseModel]] = []

        for prefix, depth, source in active_walker.discover(
            data,
            container=container,
            target_resolver=target_resolver,
            max_depth=limit,
        ):
            if max_depth is not None and max_depth >= 0 and depth > max_depth:
                raise MaxDepthExceededError(
                    path=prefix,
                    depth=depth,
                    kind=source.kind,
                    version=str(source.version[1]),
                    max_depth=max_depth,
                )
            target = target_resolver(source.kind, source)
            if target is None:
                continue
            path_steps = self._resolve_migration_path(source, target)
            hook_sets: list[tuple[Attachable, ...]] = []
            for src, dst in path_steps:
                edge = SentinelEdge.from_pair(src, dst)
                hooks = self._registry.get_hooks(edge)
                hook_sets.append(tuple(hooks))
            target_model = target.model if isinstance(target.model, type) else None
            entries.append(
                GraphEntry(
                    path=prefix,
                    source=source,
                    target=target,
                    steps=tuple(path_steps),
                    hooks=tuple(hook_sets),
                    target_model=target_model,
                )
            )

        return MigrationGraph(entries)

    def _resolve_migration_path(
        self,
        source: Versionable[VersionValue, BaseModel],
        target: Versionable[VersionValue, BaseModel],
    ) -> list[
        tuple[
            Versionable[VersionValue, BaseModel], Versionable[VersionValue, BaseModel]
        ]
    ]:
        """Return the migration path between *source* and *target* for hook lookup.

        Uses the registry's sorted version list to find adjacent steps.  Edges
        without an explicit migration are assumed backward-compatible and still
        count as a step.
        """
        if source == target:
            return []
        if source.kind != target.kind:
            return []
        kind_versions = self._registry.kind_versions(source.kind)
        try:
            lo = kind_versions.index(source)
        except ValueError as exc:
            raise RegistryError(
                self._registry.name,
                f"Source version {source} is not registered for kind {source.kind}",
            ) from exc
        try:
            hi = kind_versions.index(target)
        except ValueError as exc:
            raise RegistryError(
                self._registry.name,
                f"Target version {target} is not registered for kind {target.kind}",
            ) from exc
        path: list[
            tuple[
                Versionable[VersionValue, BaseModel],
                Versionable[VersionValue, BaseModel],
            ]
        ] = []
        step = lo
        current = source
        while step < hi:
            nxt = kind_versions[step + 1]
            path.append((current, nxt))
            current = nxt
            step += 1
        while step > hi:
            nxt = kind_versions[step - 1]
            path.append((current, nxt))
            current = nxt
            step -= 1
        return path
