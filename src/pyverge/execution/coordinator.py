"""Execution control over the frozen graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pyverge.core.types import TargetResolver
from pyverge.execution.path_resolver import PathResolver
from pyverge.execution.plan import ExecutionPlan, ExtractedEntry
from pyverge.execution.planner import ExecutionPlanner
from pyverge.execution.policy import PolicyEngine
from pyverge.execution.types import EntryExtractor


@dataclass(frozen=True, slots=True)
class ExecutionCoordinator:
    """Drive extraction, path resolution, policy, and plan construction."""

    extractor: EntryExtractor
    paths: PathResolver
    policy: PolicyEngine
    planner: ExecutionPlanner

    def extract(
        self,
        payload: dict[str, Any],
        *,
        container: type[Any] | None,
        max_depth: int,
    ) -> list[ExtractedEntry]:
        """Extract versioned entries from a payload."""
        return [
            ExtractedEntry(path, node)
            for path, _depth, node in self.extractor.extract(
                payload,
                container=container,
                max_depth=max_depth,
            )
        ]

    def plan(
        self,
        payload: dict[str, Any],
        target_resolver: TargetResolver,
        *,
        container: type[Any] | None,
        max_depth: int,
    ) -> ExecutionPlan:
        """Build a runtime plan from a payload and frozen graph."""
        entries = self.extract(
            payload,
            container=container,
            max_depth=max_depth,
        )
        path_plan = self.paths.plan(
            entries,
            target_resolver,
            container=container,
            target_fields=frozenset(),
        )
        filtered = self.policy.apply(path_plan, graph=self.paths.graph)
        return self.planner.build(filtered, payload)


__all__ = ["ExecutionCoordinator"]
