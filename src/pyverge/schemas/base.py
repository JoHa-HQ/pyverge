from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Generic

from pyverge.core.types import (
    ModelHandle,
    VersionValue,
)
from pyverge.core.versioning import (
    Comparable,
    Diff,
    Diffable,
    FieldDescriptor,
    FrozenMap,
    ModelDescriptor,
    ModelRef,
    NodeId,
    Versionable,
    VersionKey,
    VersionNode,
    parse_version,
)
from pyverge.core.versioning.diff import _build_diff
from pyverge.schemas.codec import ModelCodec
from pyverge.schemas.errors import ProviderCapabilityError
from pyverge.schemas.runtime import ModelRuntime, PythonModelRuntime


class AbstractModelAdapter(Generic[VersionValue]):
    """Shared adapter behavior: version parsing and property configuration.

    Provider-neutral: owns only version/kind property config and version
    parsing.  Field-walking (``references`` etc.) is provider-specific and
    lives in each concrete adapter.
    """

    provider: str = "custom"

    def __init__(
        self,
        codec: ModelCodec,
        runtime: ModelRuntime | None = None,
    ) -> None:
        self.model_codec = codec
        self.runtime = runtime or PythonModelRuntime()

    @property
    def version_property(self) -> str:
        return self.model_codec.version_property

    @property
    def kind_property(self) -> str:
        return self.model_codec.kind_property

    def model_id(self, handle: ModelHandle) -> str:
        return self.runtime.model_id(handle)

    def ref(self, handle: ModelHandle) -> ModelRef:
        return self.runtime.remember(
            handle,
            provider=self.provider,
            model_id=self.model_id(handle),
        )

    def resolve(self, ref: ModelRef) -> ModelHandle:
        return self.runtime.resolve(ref)

    def materialize(self, diff: Diffable[VersionValue]) -> VersionNode[VersionValue]:
        if diff.source.version > diff.target.version:
            diff = diff.inverted()
        return self.versionable(self._build_model(diff))

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
        version: str | VersionValue | None = None,
    ) -> VersionNode[VersionValue]:
        descriptor = self.model_descriptor(model_cls)
        return VersionNode[VersionValue](
            namespace=self.model_codec.namespace,
            kind=kind or self.kind(model_cls),
            version=parse_version(
                version if version is not None else self.version(model_cls)
            ),
            ref=descriptor.ref,
            descriptor=descriptor,
        )

    def versionable_from_schema(
        self,
        document: Mapping[str, Any],
        *,
        kind: str,
        version: str,
    ) -> VersionNode[VersionValue]:
        """Materialize a graph node from a JSON Schema document.

        The identity properties are injected before generation so the resulting
        model carries the same shape as a concretely registered model.
        """
        # Local import avoids a base <-> json_schema.adapter module cycle.
        from pyverge.schemas.json_schema.adapter import JsonSchemaModelAdapter  # noqa: PLC0415

        properties = dict(document.get("properties", {}))
        properties.setdefault(self.kind_property, {"type": "string", "default": kind})
        properties.setdefault(
            self.version_property, {"type": "string", "default": version}
        )
        prepared = {**document, "properties": properties}
        model = JsonSchemaModelAdapter(codec=self.model_codec).to_pydantic(
            prepared, class_name="ReflectedModel"
        )
        return self.versionable(model, kind=kind, version=version)

    def version_key(
        self,
        *,
        kind: str,
        version: str,
    ) -> VersionKey[VersionValue]:
        return self.model_codec.version_key(kind=kind, version=version)

    def _build_model(self, diff: Diffable) -> ModelHandle:
        return self.runtime.build_model(diff, codec=self.model_codec)

    def references(self, model_cls: ModelHandle) -> frozenset[NodeId]:
        raise NotImplementedError

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
