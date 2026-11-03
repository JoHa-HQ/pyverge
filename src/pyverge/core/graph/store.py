from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Generic, Protocol

from pyverge.core.types import VersionValue

from .errors import RevisionConflictError
from .graph import MigrationGraph
from .revision import Revision


@dataclass(frozen=True, slots=True)
class PublishedRevision:
    """A content revision plus its publication chronology."""

    revision: Revision
    generation: int
    generated_at: datetime


class GraphStore(Protocol[VersionValue]):
    """Optional cache/distribution seam for locked graphs.

    Stores never persist runtime callables. Correctness never depends on a
    store; it exists for cold starts, handoff, and CAS-based publication.
    """

    def save(
        self,
        graph: MigrationGraph[VersionValue],
        *,
        expected_revision: Revision | None = None,
        expected_generation: int | None = None,
    ) -> PublishedRevision: ...

    def load(self) -> MigrationGraph[VersionValue] | None: ...

    @property
    def published(self) -> PublishedRevision | None: ...


class MemoryGraphStore(Generic[VersionValue]):
    """In-memory graph store with monotonic generations and CAS checks."""

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._graph: MigrationGraph[VersionValue] | None = None
        self._published: PublishedRevision | None = None

    def save(
        self,
        graph: MigrationGraph[VersionValue],
        *,
        expected_revision: Revision | None = None,
        expected_generation: int | None = None,
    ) -> PublishedRevision:
        current = self._published
        if expected_revision is not None and (
            current is None or current.revision != expected_revision
        ):
            raise RevisionConflictError(
                "Stored revision does not match the expected revision"
            )
        if expected_generation is not None and (
            current is None or current.generation != expected_generation
        ):
            raise RevisionConflictError(
                "Stored generation does not match the expected generation"
            )
        published = PublishedRevision(
            revision=graph.revision,
            generation=1 if current is None else current.generation + 1,
            generated_at=self._clock(),
        )
        self._graph = graph
        self._published = published
        return published

    def load(self) -> MigrationGraph[VersionValue] | None:
        return self._graph

    @property
    def published(self) -> PublishedRevision | None:
        return self._published


__all__ = ["GraphStore", "MemoryGraphStore", "PublishedRevision"]
