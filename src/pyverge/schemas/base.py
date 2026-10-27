from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Generic

from pyverge.core.types import (
    ModelHandle,
    ModelVersionKey,
    VersionValue,
)
from pyverge.schemas.codec import ModelCodec
from pyverge.schemas.errors import ProviderCapabilityError
from pyverge.versioning import (
    Comparable,
    Diff,
    Diffable,
    FieldDescriptor,
    FrozenMap,
    ModelDescriptor,
    ModelRef,
    Versionable,
    VersionKey,
    VersionNode,
)
from pyverge.versioning.diff import _build_diff


class AbstractModelAdapter(Generic[VersionValue]):
    """Shared adapter behavior: version parsing and property configuration.

    Provider-neutral: owns only version/kind property config and version
    parsing.  Field-walking (``references`` etc.) is provider-specific and
    lives in each concrete adapter.
    """

    provider: str = "custom"

    def __init__(self, codec: ModelCodec) -> None:
        self.model_codec = codec

    @property
    def version_property(self) -> str:
        return self.model_codec.version_property

    @property
    def kind_property(self) -> str:
        return self.model_codec.kind_property

    def model_id(self, handle: ModelHandle) -> str:
        return self.model_codec.model_id(handle)

    def ref(self, handle: ModelHandle) -> ModelRef:
        return self.model_codec.ref(handle, provider=self.provider)

    def resolve(self, ref: ModelRef) -> ModelHandle:
        return self.model_codec.resolve(ref)

    def materialize(self, diff: Diffable[VersionValue]) -> VersionNode[VersionValue]:
        if diff.source.version > diff.target.version:
            diff = diff.inverted()
        return self.versionable(self.materialize_model(diff))

    def diff(
        self,
        source: Versionable[VersionValue],
        target: Comparable[VersionValue],
    ) -> Diff[VersionValue]:
        return _build_diff(source, target)

    def model_descriptor(self, handle: ModelHandle) -> ModelDescriptor:
        identity = {self.version_property, self.kind_property}
        fields: dict[str, FieldDescriptor] = {
            name: descriptor
            for name, descriptor in self.describe_fields(handle).items()
            if name not in identity
        }
        return ModelDescriptor(
            ref=self.ref(handle),
            fields=FrozenMap(fields),
        )

    def version(self, model_cls: ModelHandle) -> str:
        return self.model_codec.version(self.describe_fields(model_cls))

    def kind(self, model_cls: ModelHandle) -> str:
        return self.model_codec.kind(self.describe_fields(model_cls))

    def describe_fields(self, model_cls: ModelHandle) -> Mapping[str, FieldDescriptor]:
        raise NotImplementedError

    def resolve_model(self, annotation: Any) -> ModelHandle | None:
        raise NotImplementedError

    def versionable(
        self,
        model_cls: ModelHandle,
        *,
        kind: str | None = None,
        version: str | None = None,
    ) -> VersionNode[VersionValue]:
        return VersionNode[VersionValue](
            key=VersionKey[VersionValue](
                _value=self.of(version or self.version(model_cls)),
                _kind=kind or self.kind(model_cls),
            ),
            descriptor=self.model_descriptor(model_cls),
        )

    def version_key(
        self,
        *,
        kind: str,
        version: str,
    ) -> Comparable[VersionValue]:
        return self.model_codec.version_key(kind=kind, version=version)

    def materialize_model(self, diff: Diffable) -> ModelHandle:
        raise NotImplementedError

    def references(self, model_cls: ModelHandle) -> frozenset[ModelVersionKey]:
        raise NotImplementedError

    @classmethod
    def of(cls, value: str | VersionValue) -> VersionValue:
        return ModelCodec().of(value)

    def can_handle(
        self,
        container: Any,
        *,
        fields: frozenset[str] | None = None,
    ) -> bool:
        raise NotImplementedError

    def ensure_compatible(
        self,
        container: Any,
        *,
        fields: frozenset[str],
    ) -> None:
        if container is None:
            return
        if not self.can_handle(container, fields=fields):
            raise ProviderCapabilityError(
                "container is incompatible with the migration graph: "
                f"cannot cover fields {sorted(fields)}"
            )

    def fields(self, model_cls: ModelHandle) -> frozenset[str]:
        identity = {self.version_property, self.kind_property}
        return frozenset(
            name for name in self.describe_fields(model_cls) if name not in identity
        )
