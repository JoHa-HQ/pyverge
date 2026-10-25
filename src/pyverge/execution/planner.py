from __future__ import annotations

from dataclasses import dataclass
from typing import Generic

from pyverge.core.types import VersionValue
from pyverge.execution.path import Path
from pyverge.execution.plan import (
    ExecutionPlan,
    PathPlan,
    PathPlanEntry,
)


@dataclass(frozen=True, slots=True)
class ExecutionPlanner(Generic[VersionValue]):
    """Turn a PathPlan into runtime-bound levels and execution options."""

    def build(
        self, path: PathPlan[VersionValue], payload: dict
    ) -> ExecutionPlan[VersionValue]:
        return ExecutionPlan(
            path=path,
            payload=payload,
            levels=self._levels(path.entries),
        )

    def _levels(
        self, entries: tuple[PathPlanEntry, ...]
    ) -> tuple[tuple[PathPlanEntry[VersionValue], ...], ...]:
        remaining = list(entries)
        levels: list[tuple[PathPlanEntry[VersionValue], ...]] = []
        while remaining:
            ready = [
                entry
                for entry in remaining
                if not any(
                    Path(*other.path).is_descendant_of(entry.path)
                    for other in remaining
                    if other is not entry
                )
            ]
            if not ready:
                ready = [remaining[0]]
            levels.append(tuple(ready))
            chosen = {id(entry) for entry in ready}
            remaining = [entry for entry in remaining if id(entry) not in chosen]
        return tuple(levels)


__all__ = ["ExecutionPlanner"]
