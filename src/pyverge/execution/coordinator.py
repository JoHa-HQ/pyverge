from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic

from pyverge.core.types import VersionValue
from pyverge.execution.plan import ExecutionPlan, ExtractedEntry
from pyverge.execution.planner import ExecutionPlanner
from pyverge.execution.types import EntryExtractor
from pyverge.graph.planning.finder import PathFinder
from pyverge.graph.planning.targets import TargetPolicy


@dataclass(frozen=True, slots=True)
class ExecutionCoordinator(Generic[VersionValue]):
    """Drive extraction, path resolution, policy, and plan construction."""

    extractor: EntryExtractor[VersionValue]
    finder: PathFinder[VersionValue]
    planner: ExecutionPlanner[VersionValue]

    def extract(
        self,
        payload: dict[str, Any],
        *,
        container: type[Any] | None,
        max_depth: int,
    ) -> list[ExtractedEntry[VersionValue]]:
        return [
            ExtractedEntry[VersionValue](path, node)
            for path, _depth, node in self.extractor.extract(
                payload,
                container=container,
                max_depth=max_depth,
            )
        ]

    def plan(
        self,
        payload: dict[str, Any],
        target: TargetPolicy,
        *,
        container: type[Any] | None,
        max_depth: int,
    ) -> ExecutionPlan[VersionValue]:
        entries = self.extract(
            payload,
            container=container,
            max_depth=max_depth,
        )
        path_plan = self.finder.find(
            entries,
            target,
            container=container,
            target_fields=frozenset(),
        )
        return self.planner.build(path_plan, payload)


__all__ = ["ExecutionCoordinator"]
