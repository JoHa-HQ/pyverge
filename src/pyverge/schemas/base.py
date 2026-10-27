from __future__ import annotations

import logging
import types
from collections.abc import Iterable, Mapping, Sequence
from typing import (
    Annotated,
    Any,
    Generic,
    Literal,
    Union,
    get_args,
    get_origin,
)

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
    TypeKind,
    TypeRef,
    Versionable,
    VersionKey,
    VersionNode,
)
from pyverge.versioning.diff import _build_diff

_TUPLE_ELLIPSIS_ARGS = 2

_SIMPLE_TYPES: dict[Any, TypeKind] = {
    bool: TypeKind.BOOLEAN,
    int: TypeKind.INTEGER,
    float: TypeKind.NUMBER,
    str: TypeKind.STRING,
    bytes: TypeKind.BYTES,
}

logger = logging.getLogger(__name__)


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
        module = getattr(handle, "__module__", None) or type(handle).__module__
        qualname = getattr(handle, "__qualname__", None) or getattr(
            handle, "__name__", None
        )
        if qualname is None:
            return f"{module}.{type(handle).__qualname__}"
        return f"{module}.{qualname}"

    def type_ref(self, annotation: Any) -> TypeRef:  # noqa: C901, PLR0911
        if annotation is None or annotation is type(None):
            return TypeRef.null()
        if annotation is Any:
            return TypeRef.any()
        simple = _SIMPLE_TYPES.get(annotation)
        if simple is not None:
            return TypeRef.primitive(simple)

        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is Annotated:
            return self.type_ref(args[0])
        if origin is Literal:
            return TypeRef.literal(*args)
        if origin is Union or origin is types.UnionType:
            return TypeRef.union(*(self.type_ref(arg) for arg in args))
        if origin is tuple:
            if len(args) == _TUPLE_ELLIPSIS_ARGS and args[1] is Ellipsis:
                return TypeRef.array(self.type_ref(args[0]))
            return TypeRef.array(TypeRef.union(*(self.type_ref(arg) for arg in args)))
        if origin in (list, set, frozenset, Sequence, Iterable):
            return TypeRef.array(self.type_ref(args[0]))
        if origin in (dict, Mapping):
            return TypeRef.mapping(self.type_ref(args[0]), self.type_ref(args[1]))

        resolved = self.resolve_model(annotation)
        if resolved is not None:
            version = self.version(resolved)
            return TypeRef.model(
                ModelRef(provider=self.provider, model_id=self.model_id(resolved)),
                version=version or None,
            )

        if isinstance(annotation, type):
            return TypeRef.unknown(f"{annotation.__module__}.{annotation.__qualname__}")
        return TypeRef.unknown(str(annotation))

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
            ref=ModelRef(
                provider=self.provider,
                model_id=self.model_id(handle),
            ),
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
            _model=model_cls,
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
