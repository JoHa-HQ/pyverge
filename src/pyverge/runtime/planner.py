from __future__ import annotations

from dataclasses import dataclass
from typing import Generic

from pyverge.core.graph.planning.plan import PathPlan, PathPlanEntry
from pyverge.core.types import VersionValue
from pyverge.runtime.migrations import MigrationBindings
from pyverge.runtime.plan import ExecutionEntry, ExecutionPlan


@dataclass(frozen=True, slots=True)
class ExecutionPlanner(Generic[VersionValue]):
    """Bind a graph PathPlan to runtime callables, hooks, and payload levels."""

    bindings: MigrationBindings[VersionValue]

    def build(
        self, path: PathPlan[VersionValue], payload: dict
    ) -> ExecutionPlan[VersionValue]:
        bound: dict[int, ExecutionEntry[VersionValue]] = {
            id(entry): self._bind(entry) for entry in path.entries
        }
        levels = tuple(
            tuple(bound[id(entry)] for entry in level) for level in path.levels
        )
        return ExecutionPlan(path=path, payload=payload, levels=levels)

    def _bind(self, entry: PathPlanEntry[VersionValue]) -> ExecutionEntry[VersionValue]:
        definitions = tuple(self.bindings.resolve(edge) for edge in entry.edges)
        return ExecutionEntry(
            plan=entry,
            migrations=tuple(definitions),
            hooks=tuple(tuple(self.bindings.hooks(edge)) for edge in entry.edges),
        )


__all__ = ["ExecutionPlanner"]
