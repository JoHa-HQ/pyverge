from __future__ import annotations

from dataclasses import dataclass, field
from functools import total_ordering
from typing import TYPE_CHECKING, Any, Generic, Self

from pyverge.core.types import MigrationFunc, ModelData, ModelKind, VersionValue

from ..canonical import ContentHasher
from ..errors import MigrationApplicationError
from ..types import Diffable
from .metadata import EdgeRef, MigrationDescriptor, MigrationRef
from .nodes import NodeId, VersionNode

if TYPE_CHECKING:
    from pyverge.runtime.context import MigrationContext

    from ..jgf import JgfEdge


@total_ordering
@dataclass(frozen=True, slots=True, eq=False)
class EdgeKey(Generic[VersionValue]):
    """A directed edge identity plus identity-neutral storage metadata."""

    source: NodeId[VersionValue]
    target: NodeId[VersionValue]
    ref: EdgeRef = field(compare=False, hash=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.ref, EdgeRef):
            raise TypeError("EdgeKey.ref must be an EdgeRef")
        if self.source.namespace != self.target.namespace:
            raise ValueError(
                "Cross-namespace edges are forbidden: "
                f"{self.source.namespace!r} != {self.target.namespace!r}"
            )
        if self.source.kind != self.target.kind:
            raise ValueError(
                "Cross-kind edges are forbidden: "
                f"{self.source.kind!r} != {self.target.kind!r}"
            )

    @classmethod
    def from_pair(
        cls,
        source: NodeId[VersionValue],
        target: NodeId[VersionValue],
        *,
        ref: EdgeRef | None = None,
    ) -> Self:
        return cls(source=source, target=target, ref=ref or EdgeRef())

    @classmethod
    def from_version_edge(
        cls,
        edge: Any,
        *,
        ref: EdgeRef | None = None,
    ) -> Self:
        return cls(
            source=edge.source,
            target=edge.target,
            ref=ref or edge.ref,
        )

    @property
    def id(self) -> Self:
        return self

    @property
    def namespace(self) -> str:
        return self.source.namespace

    @property
    def kind(self) -> ModelKind:
        return self.source.kind

    @property
    def key(self) -> tuple[NodeId[VersionValue], NodeId[VersionValue]]:
        return self.source, self.target

    @property
    def is_executable(self) -> bool:
        return False

    def _check(self, other: object) -> EdgeKey[Any]:
        if not isinstance(other, EdgeKey):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with "
                f"{other.__class__.__name__}"
            )
        return other

    def __eq__(self, other: object) -> bool:
        candidate = self._check(other)
        return self.key == candidate.key

    def __lt__(self, other: object) -> bool:
        candidate = self._check(other)
        return self.key < candidate.key

    def __gt__(self, other: object) -> bool:
        candidate = self._check(other)
        return self.key > candidate.key

    def __hash__(self) -> int:
        return hash(self.key)

    def digest(self, hasher: ContentHasher) -> str:
        return hasher.digest(
            {
                "source": {
                    "namespace": self.source.namespace,
                    "kind": self.source.kind,
                    "version": str(self.source.version),
                },
                "target": {
                    "namespace": self.target.namespace,
                    "kind": self.target.kind,
                    "version": str(self.target.version),
                },
            }
        )

    def __str__(self) -> str:
        return f"{self.source}->{self.target}"

    def __repr__(self) -> str:
        return (
            f"EdgeKey[{type(self.source.version).__name__}]("
            f"{self.source!r}, {self.target!r})"
        )


@dataclass(frozen=True, slots=True, eq=False, kw_only=True)
class VersionEdge(EdgeKey[VersionValue]):
    """An enriched edge key that binds hydrated endpoints and an executable diff."""

    source: VersionNode[VersionValue]
    target: VersionNode[VersionValue]
    diff: Diffable[VersionValue]
    func: MigrationFunc
    migration: MigrationDescriptor

    def __post_init__(self) -> None:
        EdgeKey.__post_init__(self)
        if not isinstance(self.ref, MigrationRef):
            raise TypeError("VersionEdge.ref must be a MigrationRef")

    @property
    def id(self) -> VersionEdge[VersionValue]:
        return self

    @property
    def is_executable(self) -> bool:
        return True

    def with_diff(self, diff: Diffable[VersionValue]) -> Self:
        return type(self)(
            source=self.source,
            target=self.target,
            diff=diff,
            func=self.func,
            migration=self.migration,
            ref=self.ref,
        )

    def with_migration(self, migration: MigrationDescriptor) -> Self:
        return type(self)(
            source=self.source,
            target=self.target,
            diff=self.diff,
            func=self.func,
            migration=migration,
            ref=self.ref,
        )

    def content_payload(self, hasher: ContentHasher) -> dict[str, object]:
        return {
            "id": str(self),
            "source": self.source.content_hash(hasher),
            "target": self.target.content_hash(hasher),
            "diff": self.diff.fingerprint_payload(),
            "migration": {
                "strategy": self.migration.strategy,
                "identity": self.migration.identity,
            },
        }

    def content_hash(self, hasher: ContentHasher) -> str:
        return hasher.digest(self.content_payload(hasher))

    def to_jgf(self) -> JgfEdge:
        from ..jgf import JgfEdge  # noqa: PLC0415

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

    def __repr__(self) -> str:
        return (
            f"VersionEdge[{type(self.source.version).__name__}]("
            f"{self.source!r}, {self.target!r})"
        )


__all__ = [
    "EdgeKey",
    "VersionEdge",
]
