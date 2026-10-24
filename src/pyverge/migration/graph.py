from __future__ import annotations

import bisect
from dataclasses import dataclass
from typing import Any, Generic

from pyverge.core.errors import MaxDepthExceededError
from pyverge.core.types import (
    Attachable,
    MigrationDirectionStrategy,
    ModelHandle,
    ModelKind,
    TargetResolver,
    VersionValue,
)
from pyverge.migration.types import (
    Walker,
)
from pyverge.registry import (
    Registry,
)
from pyverge.registry.errors import CatalogError
from pyverge.versioning import (
    EdgeKey,
    VersionNode,
)


@dataclass(frozen=True, slots=True)
class GraphEntry(Generic[VersionValue]):
    """A single versioned entry discovered in a payload.

    ``steps`` is the resolved migration path, ``hooks`` the per-step hooks, and
    ``target_model`` the model to validate the migrated entry against.
    """

    path: tuple[str | int, ...]
    source: VersionNode[VersionValue]
    target: VersionNode[VersionValue]
    target_model: ModelHandle | None = None
    steps: tuple[
        tuple[VersionNode[VersionValue], VersionNode[VersionValue]],
        ...,
    ] = ()
    hooks: tuple[tuple[Attachable, ...], ...] = ()

    def allows_direction(self, direction: MigrationDirectionStrategy) -> bool:
        """Return whether this entry may migrate under *direction*.

        Direction is path-level policy: the entry owns ``source`` -> ``target``,
        which may span several edges, so the check belongs here rather than on a
        single-edge ``Diff``.
        """
        if direction == "any" or self.source == self.target:
            return True
        if direction == "forward":
            return self.source < self.target
        if direction == "backward":
            return self.source > self.target
        return True

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

    Consumed by the engine to determine migration order and parallelization
    groups.
    """

    def __init__(self, entries: list[GraphEntry[VersionValue]]) -> None:
        self._entries = entries
        self._by_path: dict[tuple[str | int, ...], GraphEntry[VersionValue]] = {
            e.path: e for e in entries
        }

    @property
    def entries(self) -> list[GraphEntry[VersionValue]]:
        """All discovered versioned entries (build order)."""
        return list(self._entries)

    def topological_order(self) -> list[GraphEntry[VersionValue]]:
        """Entries in migration order: children before parents.

        A child's path strictly extends its parent's, so sorting by path length
        descending puts children first (ties broken lexicographically).
        """
        return sorted(
            self._entries,
            key=lambda e: (-len(e.path), e.path),
        )

    def execution_levels(self) -> list[list[GraphEntry[VersionValue]]]:
        """Entries grouped by execution wave: leaves first, roots last.

        Entries within a wave are independent and can migrate in parallel.
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

        current: list[GraphEntry[VersionValue]] = [
            entries_by_path[p] for p, count in pending.items() if count == 0
        ]
        levels: list[list[GraphEntry[VersionValue]]] = []

        while current:
            current.sort(key=lambda e: e.path)
            levels.append(current)
            next_wave: list[GraphEntry[VersionValue]] = []
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

    def independent_roots(self) -> list[GraphEntry[VersionValue]]:
        """Root entry of each disjoint component — no other path is its prefix."""
        all_paths = {e.path for e in self._entries}
        roots: list[GraphEntry[VersionValue]] = []
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

    def entry_at(self, path: tuple[str | int, ...]) -> GraphEntry[VersionValue] | None:
        """Return the entry at *path*, or ``None``."""
        return self._by_path.get(path)

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)

    def __repr__(self) -> str:
        return f"MigrationGraph(entries={len(self._entries)})"


@dataclass(frozen=True)
class MigrationPlan(Generic[VersionValue]):
    """A discovered migration plan: the graph plus its execution context.

    Produced by :meth:`GraphBuilder.build` and consumed by an :class:`Executor`.
    Carries the discovered graph, the original payload, and the container the
    payload was guided by (``None`` for containerless discovery).  The executor
    owns the pre-execution compatibility gate over ``container`` + ``graph``.
    """

    data: dict[str, Any]
    graph: MigrationGraph[VersionValue]
    container: ModelHandle | None = None

    @property
    def target_fields(self) -> frozenset[str]:
        """Every field the graph's target versions produce."""
        fields: set[str] = set()
        for entry in self.graph.entries:
            fields.update(entry.target.fields)
        return frozenset(fields)

    def __len__(self) -> int:
        return len(self.graph)

    def __bool__(self) -> bool:
        return bool(self.graph)


class GraphBuilder(Generic[VersionValue]):
    """Builds a :class:`MigrationGraph` by scanning a payload for versioned dicts.

    Delegates traversal to the configured :class:`Walker`.
    """

    def __init__(
        self,
        registry: Registry[VersionValue],
        walker: Walker[VersionValue],
        *,
        max_migration_depth: int = -1,
    ) -> None:
        self._registry = registry
        self._max_migration_depth = max_migration_depth
        self._walker = walker

    @property
    def walker(self) -> Walker[VersionValue]:
        """The configured payload walker."""
        return self._walker

    def build(
        self,
        data: dict[str, Any],
        *,
        target_resolver: TargetResolver,
        container: type[Any] | None = None,
        max_depth: int | None = None,
    ) -> MigrationPlan[VersionValue]:
        """Scan *data* and return a :class:`MigrationPlan`.

        The plan carries the discovered graph, the payload, and the guiding
        container.  *max_depth* overrides ``max_migration_depth`` for this call
        (``0`` = top-level only, ``-1`` = unlimited).
        """
        active_walker = self._walker
        default_depth = self._max_migration_depth
        limit = default_depth if max_depth is None else max_depth
        entries: list[GraphEntry[VersionValue]] = []

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
            target = target_resolver(source)
            if target is None:
                continue
            path_steps = self._resolve_migration_path(source, target)
            hook_sets: list[tuple[Attachable, ...]] = []
            for src, dst in path_steps:
                edge = EdgeKey.from_pair(src, dst)
                hooks = self._registry.get_hooks(edge)
                hook_sets.append(tuple(hooks))
            target_model = target.model
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

        return MigrationPlan(
            data=data,
            graph=MigrationGraph(entries),
            container=container,
        )

    def _resolve_migration_path(
        self,
        source: VersionNode[VersionValue],
        target: VersionNode[VersionValue],
    ) -> list[tuple[VersionNode[VersionValue], VersionNode[VersionValue]]]:
        """Adjacent migration steps between *source* and *target*, for hooks.

        Uses the registry's sorted version list; an edge without an explicit
        migration still counts as a step.
        """
        if source == target:
            return []
        if source.kind != target.kind:
            return []
        kind_versions = self._registry.kind_versions(source.kind)
        lo = bisect.bisect_left(kind_versions, source)
        if lo >= len(kind_versions) or kind_versions[lo] != source:
            raise CatalogError(
                self._registry.name,
                f"Source version {source} is not registered for kind {source.kind}",
            )
        hi = bisect.bisect_left(kind_versions, target)
        if hi >= len(kind_versions) or kind_versions[hi] != target:
            raise CatalogError(
                self._registry.name,
                f"Target version {target} is not registered for kind {target.kind}",
            )
        path: list[tuple[VersionNode[VersionValue], VersionNode[VersionValue]]] = []
        step = lo
        current = kind_versions[lo]
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
