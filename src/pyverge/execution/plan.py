from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic

from pyverge.core.types import (
    DirectionViolationStrategy,
    VersionMissingStrategy,
    VersionValue,
)
from pyverge.graph.planning.plan import PathPlan, PathPlanEntry
from pyverge.versioning import VersionNode


@dataclass(frozen=True, slots=True)
class ExtractedEntry(Generic[VersionValue]):
    """One versioned node found in a payload."""

    path: tuple[str | int, ...]
    node: VersionNode[VersionValue]


@dataclass(frozen=True, slots=True)
class ExecutionPlan(Generic[VersionValue]):
    """Runtime-bound execution plan produced from a PathPlan."""

    path: PathPlan[VersionValue]
    payload: dict[str, Any]
    levels: tuple[tuple[PathPlanEntry[VersionValue], ...], ...]


@dataclass(frozen=True, slots=True)
class PlanningOptions:
    """Runtime-independent planning inputs."""

    depth_limit: int
    direction: Any
    on_direction_violation: DirectionViolationStrategy
    on_missing_path: VersionMissingStrategy
    on_missing_model: VersionMissingStrategy


__all__ = [
    "ExecutionPlan",
    "ExtractedEntry",
    "PlanningOptions",
]
