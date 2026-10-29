from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Self

from pyverge.core.context import MigrationContext
from pyverge.core.types import (
    MigrationFunc,
    ModelData,
    VersionValue,
)

from .canonical import ContentHasher
from .errors import MigrationApplicationError
from .identity import EdgeKey, NodeId, VersionKey
from .schema import (
    FieldDescriptor,
    MigrationDescriptor,
    ModelDescriptor,
    ModelRef,
)
from .types import (
    Diffable,
    Transitional,
)

if TYPE_CHECKING:
    from .jgf import JgfEdge, JgfNode


@dataclass(frozen=True, slots=True, eq=False, kw_only=True)
class VersionNode(VersionKey[VersionValue]):
    """An enriched version key that always binds a model descriptor."""

    descriptor: ModelDescriptor

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
    def model_id(self) -> str:
        return self.descriptor.ref.model_id

    @property
    def references(self) -> frozenset[NodeId[VersionValue]]:
        return self.descriptor.references

    @property
    def fields(self) -> frozenset[str]:
        return frozenset(self.descriptor.fields)

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
        return cls(
            namespace=str(value.get("namespace", "")),
            kind=str(value["kind"]),
            version=parse_version(str(value["version"])),
            descriptor=ModelDescriptor.from_canonical(
                value["model"], parse_version=parse_version
            ),
        )

    def to_canonical(self) -> dict[str, Any]:
        return {
            "namespace": self.namespace,
            "kind": self.kind,
            "version": str(self.version),
            "model": self.descriptor.to_canonical(),
        }

    def content_hash(self, hasher: ContentHasher) -> str:
        return hasher.digest(self.content_payload())

    def to_jgf(self, hasher: ContentHasher) -> JgfNode:
        from .jgf import JgfNode  # noqa: PLC0415

        return JgfNode.from_version(self, hasher)

    def __repr__(self) -> str:
        return (
            f"VersionNode[{self.strategy.__name__}]("
            f"{self.namespace!r}, {self.kind!r}, {self.version!r})"
        )


@dataclass(frozen=True, slots=True, eq=False, kw_only=True)
class VersionEdge(EdgeKey[VersionValue]):
    """An enriched edge key that binds hydrated endpoints and an executable diff."""

    source: VersionNode[VersionValue]
    target: VersionNode[VersionValue]
    diff: Diffable[VersionValue]
    func: MigrationFunc
    migration: MigrationDescriptor

    @property
    def id(self) -> VersionEdge[VersionValue]:
        return self

    @property
    def modelrefs(self) -> tuple[ModelRef, ModelRef]:
        return self.source.modelref, self.target.modelref

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

    def __repr__(self) -> str:
        return (
            f"VersionEdge[{type(self.source.version).__name__}]("
            f"{self.source!r}, {self.target!r})"
        )


__all__ = [
    "EdgeKey",
    "MigrationDescriptor",
    "NodeId",
    "Transitional",
    "VersionEdge",
    "VersionKey",
    "VersionNode",
]
