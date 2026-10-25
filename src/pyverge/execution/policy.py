"""Planning policy application."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Generic

from pyverge.core.types import (
    DepthViolationStrategy,
    DirectionViolationStrategy,
    VersionMissingStrategy,
    VersionValue,
)
from pyverge.execution.direction import DirectionPolicy
from pyverge.execution.plan import PathPlan, PathPlanEntry
from pyverge.registry import GraphCatalog
from pyverge.registry.errors import CatalogError
from pyverge.versioning import EdgeKey


@dataclass(frozen=True, slots=True)
class PolicyEngine(Generic[VersionValue]):
    """Filter a resolved path plan against path policy.

    Target and path resolution happen before this service; the engine enforces
    direction, depth, and missing-edge policy over the resolved plan.
    """

    direction: DirectionPolicy
    on_direction_violation: DirectionViolationStrategy
    on_missing_path: VersionMissingStrategy
    depth_limit: int
    on_depth_violation: DepthViolationStrategy

    def apply(
        self, plan: PathPlan[VersionValue], *, graph: GraphCatalog[VersionValue]
    ) -> PathPlan[VersionValue]:
        """Return *plan* with policy-rejected entries removed or raise."""
        kept: list[PathPlanEntry[VersionValue]] = []
        for entry in plan.entries:
            if not self.direction.allows(entry.source, entry.target):
                self._violation(
                    graph,
                    entry,
                    "direction",
                    self.on_direction_violation,
                    f"direction policy rejected {entry.source} -> {entry.target}",
                )
                continue
            if self.depth_limit >= 0 and len(entry.steps) > self.depth_limit:
                self._violation(
                    graph,
                    entry,
                    "depth",
                    self.on_depth_violation,
                    f"path depth {len(entry.steps)} exceeds limit {self.depth_limit}",
                )
                continue
            if entry.source != entry.target and not entry.steps:
                self._violation(
                    graph,
                    entry,
                    "missing path",
                    self.on_missing_path,
                    f"No migration path for {entry.source} -> {entry.target}",
                )
                continue
            if any(
                not graph.has_migration(EdgeKey.from_pair(source, target))
                for source, target in entry.steps
            ):
                self._violation(
                    graph,
                    entry,
                    "missing path",
                    self.on_missing_path,
                    f"Missing migration edge on {entry.source} -> {entry.target}",
                )
                continue
            kept.append(entry)
        return replace(plan, entries=tuple(kept))

    def _violation(
        self,
        graph: GraphCatalog[VersionValue],
        entry: PathPlanEntry[VersionValue],
        layer: str,
        strategy: str,
        message: str,
    ) -> None:
        if strategy == "raise":
            raise CatalogError(graph.name, f"{layer} policy: {message}")
        if strategy != "skip":
            raise ValueError(f"Unknown {layer} policy: {strategy!r}")


__all__ = ["PolicyEngine"]
