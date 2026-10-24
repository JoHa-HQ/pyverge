"""Version graph value objects.

These objects are the registry's index keys and stored values. They keep
generic version parameters, total ordering, hashing, inheritance, and
callability; do not flatten them into plain records.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import total_ordering
from typing import TYPE_CHECKING, Generic, Self, TypeVar

from pyverge.core.context import MigrationContext
from pyverge.core.types import (
    MigrationFunc,
    ModelData,
    ModelHandle,
    ModelKind,
    ModelVersionKey,
    VersionValue,
)

from .canonical import ContentHasher
from .errors import MigrationApplicationError
from .types import (
    Comparable,
    Diffable,
    Migratable,
    MigrationKey,
    Transitional,
)

if TYPE_CHECKING:
    from .jgf import JgfEdge, JgfNode


@total_ordering
@dataclass(frozen=True, slots=True)
class VersionKey(Generic[VersionValue]):
    """A temporary ``(kind, version)`` search key.

    Keys are not stored. Equality and ordering compare only the endpoint
    identity, so a key and a :class:`VersionNode` with the same identity are
    interchangeable inside sorted collections.
    """

    _value: VersionValue
    _kind: ModelKind

    @property
    def strategy(self) -> type[VersionValue]:
        """The concrete version type (semver, date, ordinal, ...)."""
        return type(self._value)

    @property
    def version(self) -> ModelVersionKey:
        """The ``(kind, version)`` identity pair."""
        return self._kind, self._value

    @property
    def kind(self) -> ModelKind:
        """The model family identifier."""
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

    @property
    def jgf_id(self) -> str:
        """Stable JGF node id: ``kind@version``."""
        return f"{self._kind}@{self._value}"

    def __str__(self) -> str:
        return self.jgf_id

    def __repr__(self) -> str:
        return f"VersionKey[{self.strategy.__name__}]({self._value}, {self._kind})"


@dataclass(frozen=True, slots=True, eq=False)
class VersionNode(VersionKey[VersionValue]):
    """A materialized model version that always binds a model handle.

    ``references`` is the set of versioned kinds the model's fields declare.
    ``fields`` is the model's field names minus identity fields. Neither
    participates in equality or ordering.
    """

    _model: ModelHandle
    references: frozenset[ModelVersionKey]
    fields: frozenset[str]
    model_id: str

    @property
    def model(self) -> ModelHandle:
        """The opaque provider model handle."""
        return self._model

    def content_payload(self) -> dict[str, object]:
        """Canonical schema/content payload for hashing."""
        if not self.model_id:
            raise ValueError(
                f"VersionNode {self.jgf_id} requires model_id for content hashing"
            )
        return {
            "id": self.jgf_id,
            "model": self.model_id,
            "fields": sorted(self.fields),
            "references": sorted(
                f"{kind}@{version}" for kind, version in self.references
            ),
        }

    def content_hash(self, hasher: ContentHasher) -> str:
        """Content address derived with the supplied hashing strategy."""
        return hasher.digest(self.content_payload())

    def to_jgf(self, hasher: ContentHasher) -> JgfNode:
        """Project this node into its JGF representation."""
        from .jgf import JgfNode  # noqa: PLC0415

        return JgfNode.from_version(self, hasher)

    def __repr__(self) -> str:
        model = getattr(self.model, "__name__", "model")
        return (
            f"VersionNode[{self.strategy.__name__}, {model}]"
            f"({self._value}, {self._kind})"
        )


@total_ordering
@dataclass(frozen=True, slots=True)
class EdgeKey(Generic[VersionValue]):
    """A temporary directed ``(source, target)`` edge search key."""

    source: Comparable[VersionValue]
    target: Comparable[VersionValue]

    @classmethod
    def from_pair(
        cls,
        source: Comparable[VersionValue],
        target: Comparable[VersionValue],
    ) -> Self:
        """Build an edge key from two endpoint identities."""
        return cls(source, target)

    @classmethod
    def from_version_edge(cls, edge: Migratable[VersionValue]) -> Self:
        """Build an edge key from a stored edge."""
        return cls(edge.source, edge.target)

    @property
    def kind(self) -> ModelKind:
        """The model family identifier."""
        return self.source.kind

    @property
    def key(self) -> MigrationKey:
        """The endpoint pair."""
        return (self.source, self.target)

    @property
    def edge(self) -> MigrationKey:
        """The endpoint pair (alias of :attr:`key`)."""
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

    @property
    def jgf_id(self) -> str:
        """Stable JGF edge id: ``source->target``."""
        return f"{self.source.jgf_id}->{self.target.jgf_id}"

    def __str__(self) -> str:
        return self.jgf_id


@dataclass(frozen=True, slots=True)
class MigrationIdentity:
    """Provider-supplied migration identity: strategy + stable payload identity."""

    strategy: str
    identity: str


@dataclass(frozen=True, slots=True, eq=False)
class VersionEdge(EdgeKey[VersionValue]):
    """A directed migration edge connecting two materialized versions."""

    source: VersionNode[VersionValue]
    target: VersionNode[VersionValue]
    diff: Diffable[VersionValue]
    func: MigrationFunc
    migration: MigrationIdentity

    def content_payload(self, hasher: ContentHasher) -> dict[str, object]:
        """Canonical edge payload: endpoint hashes, diff, migration, flag."""
        return {
            "id": self.jgf_id,
            "source": self.source.content_hash(hasher),
            "target": self.target.content_hash(hasher),
            "diff": self.diff.fingerprint_payload(),
            "migration": {
                "strategy": self.migration.strategy,
                "identity": self.migration.identity,
            },
        }

    def content_hash(self, hasher: ContentHasher) -> str:
        """Content address derived with the supplied hashing strategy."""
        return hasher.digest(self.content_payload(hasher))

    def to_jgf(self) -> JgfEdge:
        """Project this edge into its JGF representation."""
        from .jgf import JgfEdge  # noqa: PLC0415

        return JgfEdge.from_version_edge(self)

    def __call__(
        self,
        data: ModelData,
        context: MigrationContext | None = None,
    ) -> ModelData:
        try:
            return self.func(data, context)
        except Exception as e:
            raise MigrationApplicationError(
                self.kind,
                self.source,
                self.target,
                f"Failed to apply migration {self}: {e}",
            ) from e

    def __str__(self) -> str:
        return self.jgf_id


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ChangeSet(Generic[T]):
    """Added, removed, and modified identities in one delta."""

    added: frozenset[T] = frozenset()
    removed: frozenset[T] = frozenset()
    modified: frozenset[T] = frozenset()

    @property
    def changed(self) -> bool:
        """Whether any identity was added, removed, or modified."""
        return bool(self.added or self.removed or self.modified)

    def summary(self, label: str) -> list[str]:
        """Render non-empty change lines for *label*."""
        lines: list[str] = []
        for verb, values in (
            ("added", self.added),
            ("removed", self.removed),
            ("changed", self.modified),
        ):
            if values:
                rendered = ", ".join(str(value) for value in sorted(values, key=str))
                lines.append(f"{label} {verb}: {rendered}")
        return lines


__all__ = [
    "ChangeSet",
    "EdgeKey",
    "MigrationIdentity",
    "Transitional",
    "VersionEdge",
    "VersionKey",
    "VersionNode",
]
