from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Generic

from pyverge.core.types import ModelHandle, TargetResolver, VersionValue
from pyverge.execution.plan import ExtractedEntry, PathPlan, PathPlanEntry
from pyverge.registry import GraphCatalog
from pyverge.registry.errors import CatalogError
from pyverge.versioning import EdgeKey, VersionNode


@dataclass(frozen=True, slots=True)
class PathResolver(Generic[VersionValue]):
    """Resolve entries against a frozen graph."""

    graph: GraphCatalog[VersionValue]

    def resolve(
        self,
        entry: ExtractedEntry[VersionValue],
        target: VersionNode[VersionValue],
    ) -> PathPlanEntry[VersionValue]:
        target_node = target
        if target_node.model is None:
            raise CatalogError(
                self.graph.name,
                f"Target {target_node} has no concrete model",
            )
        steps = tuple(self.graph.migration_path(entry.node, target_node))
        hooks = tuple(
            tuple(self.graph.get_hooks(EdgeKey.from_pair(source, step_target)))
            for source, step_target in steps
        )
        migrations = tuple(
            self.graph.get_migration_by_edge(
                EdgeKey.from_pair(source, step_target)
            ).func
            for source, step_target in steps
        )
        return PathPlanEntry(
            path=entry.path,
            source=entry.node,
            target=target_node,
            target_model=target_node.model,
            steps=steps,
            hooks=hooks,
            migrations=migrations,
        )

    def plan(
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
            resolved.append(self.resolve(entry, target))
        return PathPlan(
            entries=tuple(resolved),
            container=container,
            target_fields=target_fields,
        )


__all__ = ["PathResolver"]
