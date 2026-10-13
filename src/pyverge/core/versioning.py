from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering
from typing import Any, Generic, Self, cast

from .exceptions import MigrationError
from .types import (
    Comparable,
    Diffable,
    Migratable,
    MigrationFunc,
    MigrationKey,
    ModelData,
    ModelHandle,
    ModelKind,
    ModelVersionKey,
    VersionValue,
)


@total_ordering
@dataclass(frozen=True, slots=True)
class VersionNode(Generic[VersionValue]):
    """A model version that can be either semver or ISO date.

    Optionally carries the model handle so the registry can treat
    ``(version, kind)`` as a single comparable unit.  A ``None`` model
    denotes a meta version: a ``(kind, version)`` pair with no concrete
    model content.

    ``references`` is the set of versioned kinds the model's fields *declare*
    (every union member, transitively).  It is computed once when the node is
    built and lets the graph detect a payload that could carry a versioned
    child it cannot converge — the walker silently skips unregistered kinds.

    ``fields`` is the model's field names minus the identity fields, also
    computed once by the adapter.  It lets the engine reconcile two
    registrations of the same ``(kind, version)`` without an adapter.

    Neither field participates in equality or ordering, which stay keyed on
    ``(kind, version)``.
    """

    _model: ModelHandle | None
    _value: VersionValue
    _kind: ModelKind
    references: frozenset[ModelVersionKey] = frozenset()
    fields: frozenset[str] = frozenset()

    @property
    def strategy(self) -> type[VersionValue]:
        return type(self._value)

    @property
    def model(self) -> ModelHandle | None:
        return self._model

    @property
    def version(self) -> tuple[ModelKind, VersionValue]:
        return self._kind, self._value

    @property
    def kind(self) -> ModelKind:
        return self._kind

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, VersionNode):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )

        if self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        other_c = cast(Comparable[VersionValue], other)
        return self.version < other_c.version

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, VersionNode):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        if self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        other_c = cast(Comparable[VersionValue], other)
        return self.version == other_c.version

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, VersionNode):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        if self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        other_c = cast(Comparable[VersionValue], other)
        return self.version > other_c.version

    def __hash__(self) -> int:
        return hash((self._kind, self._value))

    def __str__(self) -> str:
        return f"{self._kind}:{self._value}"

    def __repr__(self) -> str:
        if self.model is not None:
            model = getattr(self.model, "__name__", "meta")
        else:
            model = "meta"
        return f"VersionNode[{self.strategy.__name__}, {model}]({self._value}, {self._kind})"  # noqa: E501


@total_ordering
@dataclass(frozen=True, slots=True)
class VersionEdge(Generic[VersionValue]):
    """A directed migration edge connecting two versions of the same kind.

    Holds its ``source``/``target`` endpoints and the ``diff`` computed for
    the transition between them.
    """

    source: Any
    target: Any
    diff: Diffable[VersionValue]
    func: MigrationFunc

    @property
    def kind(self) -> ModelKind:
        return self.source.kind

    @property
    def key(self) -> MigrationKey:
        return (self.source, self.target)

    @property
    def edge(self) -> MigrationKey:
        return (self.source, self.target)

    def __call__(self, data: ModelData) -> ModelData:
        try:
            return self.func(data)
        except Exception as e:
            raise MigrationError(
                self.kind,
                self.source,
                self.target,
                f"Failed to apply migration {self}: {e}",
            ) from e

    def __lt__(self, other: object) -> bool:
        if isinstance(other, (VersionEdge, SentinelEdge)):
            return self.edge < other.edge
        return NotImplemented

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (VersionEdge, SentinelEdge)):
            return self.edge == other.edge
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.edge)

    def __str__(self) -> str:
        return f"VersionEdge({self.source}→{self.target})"


@total_ordering
class SentinelEdge(Generic[VersionValue]):
    """Lightweight value-only sentinel for searching across edges."""

    __slots__ = ("_source", "_target")

    def __init__(
        self,
        source: Comparable,
        target: Comparable,
    ) -> None:
        self._source = source
        self._target = target

    @classmethod
    def from_version_edge(cls, edge: Migratable[VersionValue]) -> Self:
        return cls(edge.source, edge.target)

    @classmethod
    def from_pair(
        cls,
        source: Comparable,
        target: Comparable,
    ) -> Self:
        return cls(source, target)

    @property
    def kind(self) -> ModelKind:
        return self._source.kind

    @property
    def key(self) -> MigrationKey:
        return (self._source, self._target)

    @property
    def edge(self) -> MigrationKey:
        return (self._source, self._target)

    @property
    def source(self) -> Comparable:
        return self._source

    @property
    def target(self) -> Comparable:
        return self._target

    def __lt__(self, other: object) -> bool:
        if isinstance(other, (VersionEdge, SentinelEdge)):
            return self.edge < other.edge
        return NotImplemented

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (VersionEdge, SentinelEdge)):
            return self.edge == other.edge
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.edge)

    def __str__(self) -> str:
        return f"SentinelEdge({self._source}→{self._target})"
