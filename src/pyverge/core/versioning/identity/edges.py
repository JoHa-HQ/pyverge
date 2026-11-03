from __future__ import annotations

from dataclasses import dataclass, field
from functools import total_ordering
from typing import Any, Generic, Self

from pyverge.core.types import ModelKind, VersionValue

from ..canonical import ContentHasher
from ..types import Diffable
from .metadata import EdgeRef, MigrationDescriptor, MigrationRef
from .nodes import NodeId, VersionNode

DEFAULT_DISCRIMINATOR = "default"
"""Discriminator used by legacy pair-keyed edges."""


@total_ordering
@dataclass(frozen=True, slots=True, eq=False)
class EdgeId(Generic[VersionValue]):
    """Frozen, hashable directed edge identity.

    The identity is ``source + target + discriminator``.  The discriminator
    distinguishes parallel edges between the same endpoints; it defaults to
    ``"default"`` so pair-keyed callers keep working.
    """

    source: NodeId[VersionValue]
    target: NodeId[VersionValue]
    discriminator: str = DEFAULT_DISCRIMINATOR

    def __post_init__(self) -> None:
        if not isinstance(self.discriminator, str) or not self.discriminator:
            raise ValueError("EdgeId discriminator must be a non-empty string")
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
        discriminator: str = DEFAULT_DISCRIMINATOR,
    ) -> Self:
        return cls(
            source=source,
            target=target,
            discriminator=discriminator,
        )

    @property
    def id(self) -> EdgeId[VersionValue]:
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
    def is_default_discriminator(self) -> bool:
        return self.discriminator == DEFAULT_DISCRIMINATOR

    @property
    def is_executable(self) -> bool:
        return False

    def identity(
        self,
    ) -> tuple[NodeId[VersionValue], NodeId[VersionValue], str]:
        return self.source, self.target, self.discriminator

    def digest(self, hasher: ContentHasher) -> str:
        """Return the stable identity digest for this edge."""
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
                "discriminator": self.discriminator,
            }
        )

    def _check(self, other: object) -> EdgeId[Any]:
        if not isinstance(other, EdgeId):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with "
                f"{other.__class__.__name__}"
            )
        return other

    def __eq__(self, other: object) -> bool:
        candidate = self._check(other)
        return self.identity() == candidate.identity()

    def __lt__(self, other: object) -> bool:
        candidate = self._check(other)
        return self.identity() < candidate.identity()

    def __gt__(self, other: object) -> bool:
        candidate = self._check(other)
        return self.identity() > candidate.identity()

    def __hash__(self) -> int:
        return hash(self.identity())

    def __str__(self) -> str:
        label = f"{self.source}->{self.target}"
        if self.is_default_discriminator:
            return label
        return f"{label}#{self.discriminator}"

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}[{type(self.source.version).__name__}]("
            f"{self.source!r}, {self.target!r}, "
            f"discriminator={self.discriminator!r})"
        )


@dataclass(frozen=True, slots=True, eq=False, kw_only=True)
class EdgeKey(EdgeId[VersionValue]):
    """A directed edge identity plus identity-neutral storage metadata."""

    ref: EdgeRef = field(compare=False, hash=False, repr=False)

    def __post_init__(self) -> None:
        EdgeId.__post_init__(self)
        if not isinstance(self.ref, EdgeRef):
            raise TypeError("EdgeKey.ref must be an EdgeRef")

    @classmethod
    def from_pair(
        cls,
        source: NodeId[VersionValue],
        target: NodeId[VersionValue],
        *,
        discriminator: str = DEFAULT_DISCRIMINATOR,
        ref: EdgeRef | None = None,
    ) -> Self:
        return cls(
            source=source,
            target=target,
            discriminator=discriminator,
            ref=ref or EdgeRef(),
        )

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
            discriminator=getattr(edge, "discriminator", DEFAULT_DISCRIMINATOR),
            ref=ref or edge.ref,
        )

    @property
    def id(self) -> EdgeId[VersionValue]:
        return EdgeId(
            source=self.source,
            target=self.target,
            discriminator=self.discriminator,
        )




@dataclass(frozen=True, slots=True, eq=False, kw_only=True)
class VersionEdge(EdgeKey[VersionValue]):
    """An enriched edge key that binds hydrated endpoints and an executable diff."""

    source: VersionNode[VersionValue]
    target: VersionNode[VersionValue]
    diff: Diffable[VersionValue]
    migration: MigrationDescriptor

    def __post_init__(self) -> None:
        EdgeKey.__post_init__(self)
        if not isinstance(self.ref, MigrationRef):
            raise TypeError("VersionEdge.ref must be a MigrationRef")

    @property
    def id(self) -> EdgeId[VersionValue]:
        return EdgeId(
            source=self.source,
            target=self.target,
            discriminator=self.discriminator,
        )

    @property
    def is_executable(self) -> bool:
        return True

    def with_diff(self, diff: Diffable[VersionValue]) -> Self:
        return type(self)(
            source=self.source,
            target=self.target,
            discriminator=self.discriminator,
            diff=diff,
            migration=self.migration,
            ref=self.ref,
        )

    def with_migration(self, migration: MigrationDescriptor) -> Self:
        return type(self)(
            source=self.source,
            target=self.target,
            discriminator=self.discriminator,
            diff=self.diff,
            migration=migration,
            ref=self.ref,
        )

    def content_payload(self, hasher: ContentHasher) -> dict[str, object]:
        return {
            "id": str(self),
            "source": self.source.digest(hasher),
            "target": self.target.digest(hasher),
            "discriminator": self.discriminator,
            "diff": self.diff.fingerprint_payload(),
            "migration": {
                "strategy": self.migration.strategy,
                "identity": self.migration.identity,
            },
        }

    def digest(self, hasher: ContentHasher) -> str:
        """Return the manifest checksum for this executable edge."""
        return hasher.digest(self.content_payload(hasher))


__all__ = [
    "DEFAULT_DISCRIMINATOR",
    "EdgeId",
    "EdgeKey",
    "VersionEdge",
]
