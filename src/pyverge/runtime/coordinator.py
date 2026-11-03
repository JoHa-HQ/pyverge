from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Generic

from pyverge.core.graph.planning.finder import PathFinder
from pyverge.core.graph.planning.targets import TargetPolicy
from pyverge.core.types import VersionValue
from pyverge.runtime.plan import ExecutionPlan, ExtractedEntry
from pyverge.runtime.plan_cache import PlanCache, PlanKey
from pyverge.runtime.planner import ExecutionPlanner
from pyverge.runtime.types import EntryExtractor


@dataclass(frozen=True, slots=True)
class ExecutionCoordinator(Generic[VersionValue]):
    """Drive extraction, path resolution, policy, and plan construction."""

    extractor: EntryExtractor[VersionValue]
    finder: PathFinder[VersionValue]
    planner: ExecutionPlanner[VersionValue]
    cache: PlanCache[VersionValue] = field(
        default_factory=PlanCache,
        compare=False,
        repr=False,
    )

    def extract(
        self,
        payload: dict[str, Any],
        *,
        source_model: type[Any] | None,
        max_depth: int,
    ) -> list[ExtractedEntry[VersionValue]]:
        return [
            ExtractedEntry[VersionValue](path, node)
            for path, _depth, node in self.extractor.extract(
                payload,
                source_model=source_model,
                max_depth=max_depth,
            )
        ]

    def plan(
        self,
        payload: dict[str, Any],
        target: TargetPolicy,
        *,
        source_model: type[Any] | None,
        max_depth: int,
    ) -> ExecutionPlan[VersionValue]:
        entries = self.extract(
            payload,
            source_model=source_model,
            max_depth=max_depth,
        )
        key = PlanKey.from_entries(target, source_model, entries)
        path_plan = self.cache.get(key) if key is not None else None
        if path_plan is None:
            path_plan = self.finder.find(
                entries,
                target,
                source_model=source_model,
            )
            if key is not None:
                self.cache.put(key, path_plan)
        return self.planner.build(path_plan, payload)


__all__ = ["ExecutionCoordinator"]
