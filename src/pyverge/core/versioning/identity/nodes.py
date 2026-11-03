from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from functools import total_ordering
from typing import TYPE_CHECKING, Any, Generic, Self, cast

import pendulum
from semver import Version

from pyverge.core.types import ModelKind, VersionValue

from ..errors import NodeConflictError
from .metadata import FieldDescriptor, ModelDescriptor, ModelRef, NodeRef

if TYPE_CHECKING:
    from ..canonical import ContentHasher
    from ..jgf import JgfNode


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
        if not self.namespace:
            raise ValueError("NodeId namespace must be non-empty")
        if not isinstance(self.kind, str):
            raise TypeError("NodeId kind must be a string")
        if isinstance(self.version, str):
            raise TypeError("NodeId version must be parsed; use NodeId.parse(...)")

    @classmethod
    def parse(
        cls,
        namespace: str,
        kind: ModelKind,
        version: str | VersionValue,
    ) -> Self:
        """Build a node identity, parsing its version when needed."""
        return cls(namespace=namespace, kind=kind, version=parse_version(version))

    @classmethod
    def from_string(
        cls,
        namespace: str,
        kind: ModelKind,
        version: str,
    ) -> NodeId[VersionValue]:
        return cls.parse(namespace, kind, version)

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
    """A node identity plus required, agnostic storage metadata."""

    ref: NodeRef

    def __post_init__(self) -> None:
        NodeId.__post_init__(self)
        if not isinstance(self.ref, NodeRef):
            raise TypeError("VersionKey.ref must be a NodeRef")

    @classmethod
    def parse(
        cls,
        namespace: str,
        kind: ModelKind,
        version: str | VersionValue,
        *,
        ref: NodeRef | None = None,
    ) -> Self:
        return cls(
            namespace=namespace,
            kind=kind,
            version=parse_version(version),
            ref=ref or NodeRef(),
        )

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

    @property
    def modelref(self) -> object | None:
        return None

    @property
    def is_model(self) -> bool:
        return False

    @property
    def fields(self) -> frozenset[str]:
        return frozenset()

    def reconcile(self, existing: VersionKey[VersionValue]) -> VersionKey[VersionValue]:
        return existing

    def __repr__(self) -> str:
        return (
            f"VersionKey[{self.strategy.__name__}]("
            f"{self.namespace!r}, {self.kind!r}, {self.version!r})"
        )


@dataclass(frozen=True, slots=True, eq=False, kw_only=True)
class VersionNode(VersionKey[VersionValue]):
    """An enriched version key that always binds a model descriptor."""

    descriptor: ModelDescriptor

    def __post_init__(self) -> None:
        VersionKey.__post_init__(self)
        if not isinstance(self.ref, ModelRef):
            raise TypeError("VersionNode.ref must be a ModelRef")

    @property
    def id(self) -> VersionNode[VersionValue]:
        return self

    @property
    def key(self) -> VersionKey[VersionValue]:
        return self

    @property
    def modelref(self) -> ModelRef:
        return self.descriptor.ref

    @property
    def is_model(self) -> bool:
        return True

    @property
    def model_id(self) -> str:
        return self.descriptor.ref.entity_id

    @property
    def references(self) -> frozenset[NodeId[VersionValue]]:
        return self.descriptor.references

    @property
    def fields(self) -> frozenset[str]:
        return frozenset(self.descriptor.fields)

    def reconcile(self, existing: VersionKey[VersionValue]) -> VersionKey[VersionValue]:
        if not existing.is_model:
            return self
        if self.fields != existing.fields:
            raise NodeConflictError(existing, self)
        return existing

    def with_descriptor(self, descriptor: ModelDescriptor) -> Self:
        return type(self)(
            namespace=self.namespace,
            kind=self.kind,
            version=self.version,
            ref=self.ref,
            descriptor=descriptor,
        )

    def with_fields(self, *fields: FieldDescriptor) -> Self:
        return self.with_descriptor(self.descriptor.with_fields(*fields))

    def without_fields(self, *names: str) -> Self:
        return self.with_descriptor(self.descriptor.without_fields(*names))

    def content_payload(self) -> dict[str, object]:
        if not self.model_id:
            raise ValueError(
                f"VersionNode {self} requires model_id for content hashing"
            )
        return {
            "id": str(self),
            "model": self.model_id,
            "fields": sorted(self.fields),
            "references": sorted(str(reference) for reference in self.references),
        }

    @classmethod
    def from_canonical(
        cls,
        value: Mapping[str, Any],
        *,
        parse_version: Callable[[str], Any],
    ) -> VersionNode[VersionValue]:
        descriptor = ModelDescriptor.from_canonical(
            value["model"], parse_version=parse_version
        )
        ref_value = value.get("ref")
        ref = (
            ModelRef.from_canonical(ref_value)
            if ref_value is not None
            else descriptor.ref
        )
        return cls(
            namespace=str(value["namespace"]),
            kind=str(value["kind"]),
            version=parse_version(str(value["version"])),
            ref=ref,
            descriptor=descriptor,
        )

    def to_canonical(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "kind": self.kind,
            "version": str(self.version),
            "ref": self.ref.to_canonical(),
            "model": self.descriptor.to_canonical(),
        }

    def content_hash(self, hasher: ContentHasher) -> str:
        return hasher.digest(self.content_payload())

    def to_jgf(self, hasher: ContentHasher) -> JgfNode:
        from ..jgf import JgfNode  # noqa: PLC0415

        return JgfNode.from_version(self, hasher)

    def __repr__(self) -> str:
        return (
            f"VersionNode[{self.strategy.__name__}]("
            f"{self.namespace!r}, {self.kind!r}, {self.version!r})"
        )


__all__ = [
    "NodeId",
    "VersionKey",
    "VersionNode",
    "parse_version",
]
