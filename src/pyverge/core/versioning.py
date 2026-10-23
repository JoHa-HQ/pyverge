from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering
from typing import Generic, Self

from .context import MigrationContext
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
class VersionKey(Generic[VersionValue]):
    """A temporary ``(kind, version)`` search key.

    Keys are not stored.  They identify a version during lookup, path search,
    and traversal.  Equality and ordering compare only ``(kind, version)``, so
    a key and a :class:`VersionNode` with the same identity are interchangeable
    inside sorted collections.
    """

    _value: VersionValue
    _kind: ModelKind

    @property
    def strategy(self) -> type[VersionValue]:
        return type(self._value)

    @property
    def version(self) -> tuple[ModelKind, VersionValue]:
        return self._kind, self._value

    @property
    def kind(self) -> ModelKind:
        return self._kind

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, (VersionKey, VersionNode)):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        if self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        return self.version < other.version

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, (VersionKey, VersionNode)):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        if self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        return self.version == other.version

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, (VersionKey, VersionNode)):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        if self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        return self.version > other.version

    def __hash__(self) -> int:
        return hash((self._kind, self._value))

    def __str__(self) -> str:
        return f"{self._kind}:{self._value}"

    def __repr__(self) -> str:
        return f"VersionKey[{self.strategy.__name__}]({self._value}, {self._kind})"


@dataclass(frozen=True, slots=True, eq=False)
class VersionNode(VersionKey[VersionValue]):
    """A materialized model version that always binds a model handle.

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

    _model: ModelHandle
    references: frozenset[ModelVersionKey] = frozenset()
    fields: frozenset[str] = frozenset()

    @property
    def model(self) -> ModelHandle:
        return self._model

    def __repr__(self) -> str:
        model = getattr(self.model, "__name__", "model")
        return f"VersionNode[{self.strategy.__name__}, {model}]({self._value}, {self._kind})"  # noqa: E501


@total_ordering
@dataclass(frozen=True, slots=True)
class EdgeKey(Generic[VersionValue]):
    """A temporary directed ``(source, target)`` edge search key.

    Keys are not stored.  Equality and ordering compare only the endpoint
    identities, so an edge key and a :class:`VersionEdge` with the same
    endpoints are interchangeable inside sorted collections.
    """

    source: Comparable[VersionValue]
    target: Comparable[VersionValue]

    @classmethod
    def from_pair(
        cls,
        source: Comparable[VersionValue],
        target: Comparable[VersionValue],
    ) -> Self:
        return cls(source, target)

    @classmethod
    def from_version_edge(cls, edge: Migratable[VersionValue]) -> Self:
        return cls(edge.source, edge.target)

    @property
    def kind(self) -> ModelKind:
        return self.source.kind

    @property
    def key(self) -> MigrationKey:
        return (self.source, self.target)

    @property
    def edge(self) -> MigrationKey:
        return (self.source, self.target)

    def __lt__(self, other: object) -> bool:
        if isinstance(other, EdgeKey):
            return self.edge < other.edge
        return NotImplemented

    def __eq__(self, other: object) -> bool:
        if isinstance(other, EdgeKey):
            return self.edge == other.edge
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.edge)

    def __str__(self) -> str:
        return f"EdgeKey({self.source}→{self.target})"


@dataclass(frozen=True, slots=True, eq=False)
class VersionEdge(EdgeKey[VersionValue]):
    """A directed migration edge connecting two materialized versions.

    Holds its ``source``/``target`` nodes and the ``diff`` computed for the
    transition between them.
    """

    source: VersionNode[VersionValue]
    target: VersionNode[VersionValue]
    diff: Diffable[VersionValue]
    func: MigrationFunc

    def __call__(
        self,
        data: ModelData,
        context: MigrationContext | None = None,
    ) -> ModelData:
        try:
            return self.func(data, context)
        except Exception as e:
            raise MigrationError(
                self.kind,
                self.source,
                self.target,
                f"Failed to apply migration {self}: {e}",
            ) from e

    def __str__(self) -> str:
        return f"VersionEdge({self.source}→{self.target})"
