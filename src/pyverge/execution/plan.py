from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic

from pyverge.core.types import (
    Attachable,
    DirectionViolationStrategy,
    MigrationFunc,
    ModelHandle,
    VersionMissingStrategy,
    VersionValue,
)
from pyverge.versioning import ModelRef, VersionNode


@dataclass(frozen=True, slots=True)
class ExtractedEntry(Generic[VersionValue]):
    """One versioned node found in a payload."""

    path: tuple[str | int, ...]
    node: VersionNode[VersionValue]


@dataclass(frozen=True, slots=True)
class PathPlanEntry(Generic[VersionValue]):
    """One extracted entry resolved to a concrete target path."""

    path: tuple[str | int, ...]
    source: VersionNode[VersionValue]
    target: VersionNode[VersionValue]
    target_model: ModelRef
    steps: tuple[tuple[VersionNode[VersionValue], VersionNode[VersionValue]], ...]
    hooks: tuple[tuple[Attachable, ...], ...]
    migrations: tuple[MigrationFunc, ...]


@dataclass(frozen=True, slots=True)
class PathPlan(Generic[VersionValue]):
    """Payload-level migration plan independent of execution strategy."""

    entries: tuple[PathPlanEntry[VersionValue], ...]
    container: ModelHandle | None
    target_fields: frozenset[str]


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Outcome of evaluating one entry against planning policy."""

    entry: PathPlanEntry | None
    reason: str | None


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
    "PathPlan",
    "PathPlanEntry",
    "PlanningOptions",
    "PolicyDecision",
]
