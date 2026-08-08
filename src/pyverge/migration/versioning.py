"""Model version: supports semver and calendar date versioning.

Semver: ``1.0.0``, ``2.1.0-beta``, ``0.1.1.dev7``
Date:   ``2024-06-01``, ``2025-03-15``
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering
from typing import Generic, Self, cast

from .exceptions import MigrationError
from .types import (
    Comparable,
    Diffable,
    Migratable,
    MigrationFunc,
    MigrationKey,
    ModelData,
    ModelKind,
    ModelVersionKey,
    Versionable,
    VersionValue_co,
    VModel_co,
    VSource_co,
    VTarget_co,
)


@total_ordering
@dataclass(frozen=True, slots=True)
class VersionNode(Generic[VersionValue_co, VModel_co]):
    """A model version that can be either semver or ISO date.

    Optionally carries the Pydantic model class so the registry can
    treat ``(version, kind)`` as a single comparable unit.
    """

    _model: type[VModel_co]
    _value: VersionValue_co
    _kind: ModelKind

    @property
    def strategy(self) -> type[VersionValue_co]:
        return type(self._value)

    @property
    def model(self) -> type[VModel_co]:
        return self._model

    @property
    def version(self) -> tuple[ModelKind, VersionValue_co]:
        return self._kind, self._value

    @property
    def kind(self) -> ModelKind:
        return self._kind

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, (VersionNode, SentinelNode)):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )

        if self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        other_c = cast(Comparable[VersionValue_co], other)
        return self.version < other_c.version

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, (VersionNode, SentinelNode)):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        if self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        other_c = cast(Comparable[VersionValue_co], other)
        return self.version == other_c.version

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, (VersionNode, SentinelNode)):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        if self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        other_c = cast(Comparable[VersionValue_co], other)
        return self.version > other_c.version

    def __hash__(self) -> int:
        return hash((self._kind, self._value))

    def __str__(self) -> str:
        return f"{self._kind}:{self._value}"

    def __repr__(self) -> str:
        return f"VersionNode[{self.strategy.__name__}, {self.model.__name__}]({self._value}, {self._kind})"  # noqa: E501


@total_ordering
@dataclass(frozen=True, slots=True)
class SentinelNode(Generic[VersionValue_co]):
    """Lightweight value-only sentinel for searching across versions.

    Carries no model binding — only the version value — so the registry
    can search by version string without constructing a full VersionedModel.
    """

    _kind: ModelKind
    _value: VersionValue_co

    @classmethod
    def from_version(cls, version: VersionNode) -> Self:
        return cls(version._kind, version._value)

    @property
    def strategy(self) -> type[VersionValue_co]:
        return type(self._value)

    @property
    def kind(self) -> ModelKind:
        return self._kind

    @property
    def version(self) -> ModelVersionKey:
        return (self._kind, self._value)

    @property
    def model(self) -> None:
        return None

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, (VersionNode, SentinelNode)):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        if self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        other_c = cast(Comparable[VersionValue_co], other)
        return self.version < other_c.version

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, (VersionNode, SentinelNode)):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        if self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        other_c = cast(Comparable[VersionValue_co], other)
        return self.version == other_c.version

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, (VersionNode, SentinelNode)):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with {other.__class__.__name__}"  # noqa: E501
            )
        if self.strategy != other.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with {other.strategy.__name__}"  # noqa: E501
            )
        other_c = cast(Comparable[VersionValue_co], other)
        return self.version > other_c.version

    def __hash__(self) -> int:
        return hash((self._kind, self._value))

    def __str__(self) -> str:
        return f"{self._kind}:{self._value}"


@total_ordering
@dataclass(frozen=True, slots=True)
class VersionEdge(Generic[VersionValue_co, VSource_co, VTarget_co]):
    """A directed migration edge connecting two versions of the same kind."""

    diff: Diffable[VersionValue_co]
    func: MigrationFunc

    @property
    def kind(self) -> ModelKind:
        return self.diff.kind

    @property
    def key(self) -> MigrationKey:
        return self.diff.edge

    @property
    def edge(self) -> MigrationKey:
        return self.diff.edge

    @property
    def source(self) -> Versionable[VersionValue_co, VSource_co]:
        return self.diff.source

    @property
    def target(self) -> Versionable[VersionValue_co, VTarget_co]:
        return self.diff.target

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
            return self.diff.edge < other.edge
        return NotImplemented

    def __eq__(self, other: object) -> bool:
        if isinstance(other, (VersionEdge, SentinelEdge)):
            return self.diff.edge == other.edge
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self.diff.edge)

    def __str__(self) -> str:
        return f"VersionEdge({self.diff.source}→{self.diff.target})"


class SentinelEdge(Generic[VersionValue_co, VSource_co, VTarget_co]):
    """Key-only edge sentinel, symmetric to :class:`SentinelNode`.

    Stores just the source and target versions — no ``Diffable``.
    """

    __slots__ = ("_source", "_target")

    def __init__(
        self,
        source: Versionable[VersionValue_co, VSource_co],
        target: Versionable[VersionValue_co, VTarget_co],
    ) -> None:
        self._source = source
        self._target = target

    @classmethod
    def from_version_edge(
        cls, edge: Migratable[VersionValue_co, VSource_co, VTarget_co]
    ) -> Self:
        return cls(edge.source, edge.target)

    @classmethod
    def from_pair(
        cls,
        source: Versionable[VersionValue_co, VSource_co],
        target: Versionable[VersionValue_co, VTarget_co],
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
    def source(self) -> Versionable[VersionValue_co, VSource_co]:
        return self._source

    @property
    def target(self) -> Versionable[VersionValue_co, VTarget_co]:
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
