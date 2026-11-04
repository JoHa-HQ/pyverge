from __future__ import annotations

from dataclasses import dataclass
from typing import Generic

from pyverge.core.graph.planning.path import Path
from pyverge.core.types import ModelHandle, VersionValue
from pyverge.core.versioning import EdgeId, ModelRef, VersionNode


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
    edges: tuple[EdgeId[VersionValue], ...]


@dataclass(frozen=True, slots=True)
class PathPlan(Generic[VersionValue]):
    """Graph-level migration plan independent of execution strategy."""

    entries: tuple[PathPlanEntry[VersionValue], ...]
    source_model: ModelHandle | None

    @property
    def levels(self) -> tuple[tuple[PathPlanEntry[VersionValue], ...], ...]:
        remaining = list(self.entries)
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


__all__ = ["ExtractedEntry", "PathPlan", "PathPlanEntry"]
