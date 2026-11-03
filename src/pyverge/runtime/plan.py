from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic

from pyverge.core.graph.planning.plan import PathPlan, PathPlanEntry
from pyverge.core.types import VersionValue
from pyverge.core.versioning import VersionNode


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


__all__ = [
    "ExecutionPlan",
    "ExtractedEntry",
]
