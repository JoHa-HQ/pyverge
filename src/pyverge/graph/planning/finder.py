from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Generic

from pyverge.core.types import (
    Attachable,
    MigrationFunc,
    ModelHandle,
    TargetResolver,
    VersionValue,
)
from pyverge.graph.planning.plan import PathPlan, PathPlanEntry
from pyverge.graph.planning.policy import PolicyEngine
from pyverge.graph.planning.targets import TargetCompiler, TargetPolicy
from pyverge.graph.types import GraphView, MigrationResolver
from pyverge.versioning import EdgeKey, NodeId, VersionNode

if TYPE_CHECKING:
    from pyverge.execution.plan import ExtractedEntry


@dataclass(frozen=True, slots=True)
class PathFinder(Generic[VersionValue]):
    """Resolve graph paths, apply target policy, and filter path plans."""

    graph: GraphView[VersionValue]
    targets: TargetCompiler[VersionValue]
    policy: PolicyEngine[VersionValue]
    migrations: MigrationResolver[VersionValue]
    _cache: dict[
        tuple[NodeId, NodeId],
        tuple[
            tuple[tuple[VersionNode[VersionValue], VersionNode[VersionValue]], ...],
            tuple[tuple[Attachable, ...], ...],
            tuple[MigrationFunc, ...],
        ],
    ] = field(default_factory=dict, compare=False, repr=False)

    def find(
        self,
        entries: Sequence[ExtractedEntry[VersionValue]],
        target: TargetPolicy,
        *,
        container: ModelHandle | None,
        target_fields: frozenset[str],
    ) -> PathPlan[VersionValue]:
        resolver = self.targets.compile(target)
        plan = self._plan(
            entries, resolver, container=container, target_fields=target_fields
        )
        return self.policy.apply(plan, graph=self.graph)

    def _plan(
        self,
        entries: Sequence[ExtractedEntry[VersionValue]],
        target_resolver: TargetResolver,
        *,
        container: ModelHandle | None,
        target_fields: frozenset[str],
    ) -> PathPlan[VersionValue]:
        resolved: list[PathPlanEntry[VersionValue]] = []
        for entry in entries:
            target = target_resolver(entry.node)
            if target is None:
                continue
            resolved.append(self._resolve(entry, target))
        return PathPlan(
            entries=tuple(resolved),
            container=container,
            target_fields=target_fields,
        )

    def _resolve(
        self,
        entry: ExtractedEntry[VersionValue],
        target: VersionNode[VersionValue],
    ) -> PathPlanEntry[VersionValue]:
        cache_key = (entry.node.id, target.id)
        cached = self._cache.get(cache_key)
        if cached is None:
            steps = tuple(self.graph.migration_path(entry.node, target))
            hooks = tuple(
                tuple(self.migrations.hooks(EdgeKey.from_pair(source, step_target)))
                for source, step_target in steps
            )
            migrations = tuple(
                self.migrations.resolve(EdgeKey.from_pair(source, step_target)).func
                for source, step_target in steps
            )
            self._cache[cache_key] = (steps, hooks, migrations)
        else:
            steps, hooks, migrations = cached
        return PathPlanEntry(
            path=entry.path,
            source=entry.node,
            target=target,
            target_model=target.descriptor.ref,
            steps=steps,
            hooks=hooks,
            migrations=migrations,
        )


__all__ = ["PathFinder"]
