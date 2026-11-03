from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Generic, cast

from pyverge.core.graph.planning.plan import ExtractedEntry, PathPlan, PathPlanEntry
from pyverge.core.graph.planning.policy import PolicyEngine
from pyverge.core.graph.planning.targets import (
    TargetCompiler,
    TargetPolicy,
    TargetResolver,
)
from pyverge.core.graph.types import PathGraphView
from pyverge.core.types import ModelHandle, VersionValue
from pyverge.core.versioning import (
    DEFAULT_DISCRIMINATOR,
    EdgeId,
    NodeId,
    VersionNode,
)


@dataclass(frozen=True, slots=True)
class ResolvedPath(Generic[VersionValue]):
    """Cached graph-identity resolution for one source/target pair."""

    steps: tuple[tuple[VersionNode[VersionValue], VersionNode[VersionValue]], ...]
    edges: tuple[EdgeId[VersionValue], ...]


@dataclass(frozen=True, slots=True)
class PathFinder(Generic[VersionValue]):
    """Resolve graph paths, apply target policy, and filter path plans."""

    graph: PathGraphView[VersionValue]
    targets: TargetCompiler[VersionValue]
    policy: PolicyEngine[VersionValue]
    discriminator: str = DEFAULT_DISCRIMINATOR
    _cache: dict[tuple[NodeId, NodeId], ResolvedPath[VersionValue]] = field(
        default_factory=dict, compare=False, repr=False
    )

    def find(
        self,
        entries: Sequence[ExtractedEntry[VersionValue]],
        target: TargetPolicy,
        *,
        source_model: ModelHandle | None,
    ) -> PathPlan[VersionValue]:
        resolver = self.targets.compile(target)
        plan = self._plan(entries, resolver, source_model=source_model)
        return self.policy.apply(plan, graph=self.graph)

    def _plan(
        self,
        entries: Sequence[ExtractedEntry[VersionValue]],
        target_resolver: TargetResolver,
        *,
        source_model: ModelHandle | None,
    ) -> PathPlan[VersionValue]:
        resolved: list[PathPlanEntry[VersionValue]] = []
        for entry in entries:
            target = target_resolver(entry.node)
            if target is None:
                continue
            resolved.append(self._resolve(entry, target))
        return PathPlan(
            entries=tuple(resolved),
            source_model=source_model,
        )

    def _resolve(
        self,
        entry: ExtractedEntry[VersionValue],
        target: VersionNode[VersionValue],
    ) -> PathPlanEntry[VersionValue]:
        cache_key = (entry.node.id, target.id)
        cached = self._cache.get(cache_key)
        if cached is None:
            path = tuple(
                self.graph.edge_path(
                    entry.node,
                    target,
                    discriminator=self.discriminator,
                )
            )
            steps = tuple(
                (
                    cast("VersionNode[VersionValue]", edge.source),
                    cast("VersionNode[VersionValue]", edge.target),
                )
                for edge in path
            )
            edges = tuple(edge.id for edge in path)
            resolved = ResolvedPath(steps=steps, edges=edges)
            self._cache[cache_key] = resolved
        else:
            resolved = cached
        return PathPlanEntry(
            path=entry.path,
            source=entry.node,
            target=target,
            target_model=target.descriptor.ref,
            steps=resolved.steps,
            edges=resolved.edges,
        )


__all__ = ["PathFinder", "ResolvedPath"]
