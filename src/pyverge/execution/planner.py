from __future__ import annotations

from dataclasses import dataclass
from typing import Generic

from pyverge.core.types import VersionValue
from pyverge.execution.plan import ExecutionPlan
from pyverge.graph.planning.plan import PathPlan


@dataclass(frozen=True, slots=True)
class ExecutionPlanner(Generic[VersionValue]):
    """Bind a graph PathPlan to a payload and its execution levels."""

    def build(
        self, path: PathPlan[VersionValue], payload: dict
    ) -> ExecutionPlan[VersionValue]:
        return ExecutionPlan(path=path, payload=payload, levels=path.levels)


__all__ = ["ExecutionPlanner"]
