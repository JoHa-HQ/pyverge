from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import total_ordering
from typing import TYPE_CHECKING, Any, Generic, Self, cast

import pendulum
from semver import Version

from pyverge.core.types import ModelKind, VersionValue

if TYPE_CHECKING:
    from .canonical import ContentHasher
    from .types import KeyRef


def parse_version(value: str | VersionValue) -> VersionValue:
    """Parse a semver or ISO-date string into a version value."""
    if isinstance(value, Version) or (
        isinstance(value, pendulum.Date) and not isinstance(value, pendulum.DateTime)
    ):
        return cast("VersionValue", value)

    if not isinstance(value, str):
        msg = f"Cannot parse version {value!r}: expected a string or VersionValue."
        raise TypeError(msg)

    try:
        return cast("VersionValue", Version.parse(value))
    except ValueError:
        pass

    try:
        parsed = pendulum.parse(str(value), exact=True)
        if isinstance(parsed, pendulum.DateTime):
            parsed = parsed.date()
        if not isinstance(parsed, pendulum.Date):
            raise ValueError(f"Expected date, got {parsed!r}")
        return cast("VersionValue", parsed)
    except ValueError:
        pass

    msg = (
        f"Cannot parse version {value!r}. "
        "Expected semver (e.g. '1.0.0') or ISO date (e.g. '2024-06-01')."
    )
    raise ValueError(msg)


@total_ordering
@dataclass(frozen=True, slots=True, eq=False)
class NodeId(Generic[VersionValue]):
    """Frozen, hashable graph identity: namespace + kind + parsed version."""

    namespace: str
    kind: ModelKind
    version: VersionValue

    def __post_init__(self) -> None:
        if not isinstance(self.namespace, str):
            raise TypeError("NodeId namespace must be a string")
        if not isinstance(self.kind, str):
            raise TypeError("NodeId kind must be a string")
        if isinstance(self.version, str):
            object.__setattr__(self, "version", parse_version(self.version))

    @classmethod
    def from_string(
        cls,
        namespace: str,
        kind: ModelKind,
        version: str,
    ) -> NodeId[VersionValue]:
        return cls(namespace=namespace, kind=kind, version=parse_version(version))

    @property
    def id(self) -> NodeId[VersionValue]:
        return self

    @property
    def strategy(self) -> type[VersionValue]:
        return type(self.version)

    def identity(self) -> tuple[str, ModelKind, VersionValue]:
        return self.namespace, self.kind, self.version

    def with_namespace(self, namespace: str) -> Self:
        return replace(self, namespace=namespace)

    def _check(self, other: object) -> NodeId[Any]:
        if not isinstance(other, NodeId):
            raise NotImplementedError(
                f"Cannot compare {self.__class__.__name__} with "
                f"{other.__class__.__name__}"
            )
        return other

    def __eq__(self, other: object) -> bool:
        candidate = self._check(other)
        if self.strategy is not candidate.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with "
                f"{candidate.strategy.__name__}"
            )
        return self.identity() == candidate.identity()

    def __lt__(self, other: object) -> bool:
        candidate = self._check(other)
        if self.strategy is not candidate.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with "
                f"{candidate.strategy.__name__}"
            )
        return self.identity() < candidate.identity()

    def __gt__(self, other: object) -> bool:
        candidate = self._check(other)
        if self.strategy is not candidate.strategy:
            raise TypeError(
                f"Cannot compare {self.strategy.__name__} with "
                f"{candidate.strategy.__name__}"
            )
        return self.identity() > candidate.identity()

    def __hash__(self) -> int:
        return hash(self.identity())

    def __str__(self) -> str:
        if self.namespace:
            return f"{self.namespace}:{self.kind}@{self.version}"
        return f"{self.kind}@{self.version}"

    def __repr__(self) -> str:
        return (
            f"NodeId[{self.strategy.__name__}]("
            f"{self.namespace!r}, {self.kind!r}, {self.version!r})"
        )


@dataclass(frozen=True, slots=True, eq=False, kw_only=True)
class VersionKey(NodeId[VersionValue]):
    """A node identity plus identity-neutral storage metadata."""

    ref: KeyRef | None = None

    def digest(self, hasher: ContentHasher) -> str:
        return hasher.digest(
            {
                "namespace": self.namespace,
                "kind": self.kind,
                "version": str(self.version),
            }
        )

    @property
    def key(self) -> VersionKey[VersionValue]:
        return self

    def __repr__(self) -> str:
        return (
            f"VersionKey[{self.strategy.__name__}]("
            f"{self.namespace!r}, {self.kind!r}, {self.version!r})"
        )


@total_ordering
@dataclass(frozen=True, slots=True, eq=False)
class EdgeKey(Generic[VersionValue]):
    """A directed edge identity plus identity-neutral storage metadata."""

    source: NodeId[VersionValue]
    target: NodeId[VersionValue]
    ref: KeyRef | None = field(default=None, compare=False, hash=False, repr=False)

    def __post_init__(self) -> None:
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
        ref: KeyRef | None = None,
    ) -> Self:
        return cls(source=source, target=target, ref=ref)

    @classmethod
    def from_version_edge(
        cls,
        edge: Any,
        *,
        ref: KeyRef | None = None,
    ) -> Self:
        return cls(source=edge.source, target=edge.target, ref=ref)

    @property
    def namespace(self) -> str:
        return self.source.namespace

    @property
    def kind(self) -> ModelKind:
        return self.source.kind

    @property
    def key(self) -> tuple[NodeId[VersionValue], NodeId[VersionValue]]:
        return self.source, self.target

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


__all__ = [
    "EdgeKey",
    "NodeId",
    "VersionKey",
    "parse_version",
]
