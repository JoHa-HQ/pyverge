"""Planning data contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pyverge.core.types import Attachable, MigrationFunc, ModelHandle
from pyverge.versioning import VersionNode


@dataclass(frozen=True, slots=True)
class ExtractedEntry:
    """One versioned node found in a payload."""

    path: tuple[str | int, ...]
    node: VersionNode


@dataclass(frozen=True, slots=True)
class PathPlanEntry:
    """One extracted entry resolved to a concrete target path."""

    path: tuple[str | int, ...]
    source: VersionNode
    target: VersionNode
    target_model: ModelHandle
    steps: tuple[tuple[VersionNode, VersionNode], ...]
    hooks: tuple[tuple[Attachable, ...], ...]
    migrations: tuple[MigrationFunc, ...]


@dataclass(frozen=True, slots=True)
class PathPlan:
    """Payload-level migration plan independent of execution strategy."""

    entries: tuple[PathPlanEntry, ...]
    container: ModelHandle | None
    target_fields: frozenset[str]


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Outcome of evaluating one entry against planning policy."""

    entry: PathPlanEntry | None
    reason: str | None


@dataclass(frozen=True, slots=True)
class BackendDeclaration:
    """Backend selected for an execution plan."""

    name: str
    strategy: Literal["sequential", "parallel"]
    middleware: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ExecutionPlan:
    """Runtime-bound execution plan produced from a PathPlan."""

    path: PathPlan
    payload: dict[str, Any]
    levels: tuple[tuple[PathPlanEntry, ...], ...]
    backend: BackendDeclaration


@dataclass(frozen=True, slots=True)
class PlanningOptions:
    """Runtime-independent planning inputs."""

    depth_limit: int
    direction: Any
    on_direction_violation: str
    on_missing_path: str
    on_missing_model: str


__all__ = [
    "BackendDeclaration",
    "ExecutionPlan",
    "ExtractedEntry",
    "PathPlan",
    "PathPlanEntry",
    "PlanningOptions",
    "PolicyDecision",
]
