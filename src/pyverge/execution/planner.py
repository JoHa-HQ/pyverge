"""Execution plan construction."""

from __future__ import annotations

from dataclasses import dataclass

from pyverge.execution.path import Path
from pyverge.execution.plan import (
    BackendDeclaration,
    ExecutionPlan,
    PathPlan,
    PathPlanEntry,
)


@dataclass(frozen=True, slots=True)
class ExecutionPlanner:
    """Turn a PathPlan into runtime-bound levels and execution options."""

    backend: BackendDeclaration

    def build(self, path: PathPlan, payload: dict) -> ExecutionPlan:
        """Group entries into dependency levels and attach execution options."""
        return ExecutionPlan(
            path=path,
            payload=payload,
            levels=self._levels(path.entries),
            backend=self.backend,
        )

    def _levels(
        self, entries: tuple[PathPlanEntry, ...]
    ) -> tuple[tuple[PathPlanEntry, ...], ...]:
        remaining = list(entries)
        levels: list[tuple[PathPlanEntry, ...]] = []
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
