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
from pyverge.graph.types import MigrationResolver, PathGraphView
from pyverge.versioning import EdgeKey, MigrationDescriptor, NodeId, VersionNode

if TYPE_CHECKING:
    from pyverge.execution.plan import ExtractedEntry


@dataclass(frozen=True, slots=True)
class ResolvedPath(Generic[VersionValue]):
    """Cached graph-identity resolution for one source/target pair."""

    steps: tuple[tuple[VersionNode[VersionValue], VersionNode[VersionValue]], ...]
    hooks: tuple[tuple[Attachable, ...], ...]
    migrations: tuple[MigrationFunc, ...]
    descriptors: tuple[MigrationDescriptor, ...]


@dataclass(frozen=True, slots=True)
class PathFinder(Generic[VersionValue]):
    """Resolve graph paths, apply target policy, and filter path plans."""

    graph: PathGraphView[VersionValue]
    targets: TargetCompiler[VersionValue]
    policy: PolicyEngine[VersionValue]
    migrations: MigrationResolver[VersionValue]
    _cache: dict[tuple[NodeId, NodeId], ResolvedPath[VersionValue]] = field(
        default_factory=dict, compare=False, repr=False
    )

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
            definitions = tuple(
                self.migrations.resolve(EdgeKey.from_pair(source, step_target))
                for source, step_target in steps
            )
            resolved = ResolvedPath(
                steps=steps,
                hooks=hooks,
                migrations=tuple(definition.func for definition in definitions),
                descriptors=tuple(definition.migration for definition in definitions),
            )
            self._cache[cache_key] = resolved
        else:
            resolved = cached
        return PathPlanEntry(
            path=entry.path,
            source=entry.node,
            target=target,
            target_model=target.descriptor.ref,
            steps=resolved.steps,
            hooks=resolved.hooks,
            migrations=resolved.migrations,
            migration_descriptors=resolved.descriptors,
        )


__all__ = ["PathFinder", "ResolvedPath"]
