from __future__ import annotations

import types
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import replace
from typing import (
    Annotated,
    Any,
    Literal,
    Protocol,
    Union,
    get_args,
    get_origin,
    runtime_checkable,
)

from pydantic import BaseModel, TypeAdapter, create_model
from pydantic_core import PydanticUndefined

from pyverge.core.types import ModelData, ModelHandle, ModelVersionKey, VersionValue
from pyverge.schemas.codec import ModelCodec
from pyverge.versioning import (
    NO_DEFAULT,
    Diffable,
    FieldDescriptor,
    ModelRef,
    TypeKind,
    TypeRef,
    default_canonicalizer,
)

_TUPLE_ELLIPSIS_ARGS = 2

_SIMPLE_TYPES: dict[Any, TypeKind] = {
    bool: TypeKind.BOOLEAN,
    int: TypeKind.INTEGER,
    float: TypeKind.NUMBER,
    str: TypeKind.STRING,
    bytes: TypeKind.BYTES,
}


def annotation_type_ref(  # noqa: C901, PLR0911
    annotation: Any,
    *,
    resolve_model: Callable[[Any], ModelHandle | None],
    model_ref: Callable[[ModelHandle], ModelRef],
    version: Callable[[ModelHandle], str],
) -> TypeRef:
    """Project a Python annotation into canonical ``TypeRef`` form."""
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
        return annotation_type_ref(
            args[0],
            resolve_model=resolve_model,
            model_ref=model_ref,
            version=version,
        )
    if origin is Literal:
        return TypeRef.literal(*args)
    if origin is Union or origin is types.UnionType:
        return TypeRef.union(
            *(
                annotation_type_ref(
                    arg,
                    resolve_model=resolve_model,
                    model_ref=model_ref,
                    version=version,
                )
                for arg in args
            )
        )
    if origin is tuple:
        if len(args) == _TUPLE_ELLIPSIS_ARGS and args[1] is Ellipsis:
            return TypeRef.array(
                annotation_type_ref(
                    args[0],
                    resolve_model=resolve_model,
                    model_ref=model_ref,
                    version=version,
                )
            )
        return TypeRef.array(
            TypeRef.union(
                *(
                    annotation_type_ref(
                        arg,
                        resolve_model=resolve_model,
                        model_ref=model_ref,
                        version=version,
                    )
                    for arg in args
                )
            )
        )
    if origin in (list, set, frozenset, Sequence, Iterable):
        return TypeRef.array(
            annotation_type_ref(
                args[0],
                resolve_model=resolve_model,
                model_ref=model_ref,
                version=version,
            )
        )
    if origin in (dict, Mapping):
        return TypeRef.mapping(
            annotation_type_ref(
                args[0],
                resolve_model=resolve_model,
                model_ref=model_ref,
                version=version,
            ),
            annotation_type_ref(
                args[1],
                resolve_model=resolve_model,
                model_ref=model_ref,
                version=version,
            ),
        )

    resolved = resolve_model(annotation)
    if resolved is not None:
        return TypeRef.model(model_ref(resolved), version=version(resolved) or None)

    if isinstance(annotation, type):
        return TypeRef.unknown(f"{annotation.__module__}.{annotation.__qualname__}")
    return TypeRef.unknown(str(annotation))


@runtime_checkable
class ModelRuntime(Protocol):
    """Language/runtime mechanics used by model adapters."""

    def remember(
        self,
        handle: ModelHandle,
        *,
        provider: str,
        model_id: str | None = None,
    ) -> ModelRef: ...
    def resolve(self, ref: ModelRef) -> ModelHandle: ...
    def model_id(self, handle: ModelHandle) -> str: ...

    def materialize(
        self, container: ModelHandle, data: ModelData, *, strict: bool = False
    ) -> Any: ...
    def serialize(self, model: object) -> ModelData: ...
    def validate(
        self, container: ModelHandle, data: ModelData, *, strict: bool = False
    ) -> ModelData: ...

    def identify(self, model_cls: ModelHandle) -> bool: ...
    def can_handle(
        self, container: Any, *, fields: frozenset[str] | None = None
    ) -> bool: ...
    def resolve_model(self, annotation: Any) -> ModelHandle | None: ...
    def field_model(
        self, parent_model: ModelHandle, field_name: str
    ) -> ModelHandle | None: ...
    def references(
        self,
        model_cls: ModelHandle,
        *,
        provider: str,
        codec: ModelCodec,
    ) -> frozenset[ModelVersionKey]: ...
    def describe_fields(
        self,
        model_cls: ModelHandle,
        *,
        provider: str,
        codec: ModelCodec,
    ) -> dict[str, FieldDescriptor]: ...
    def type_ref(
        self,
        annotation: Any,
        *,
        provider: str,
        codec: ModelCodec,
    ) -> TypeRef: ...
    def materialize_model(
        self,
        diff: Diffable[VersionValue],
        *,
        codec: ModelCodec,
    ) -> ModelHandle: ...


class PythonModelRuntime:
    """Python/Pydantic runtime: TypeAdapter cache and native handle registry."""

    def __init__(self) -> None:
        self._adapters: dict[Any, TypeAdapter[Any]] = {}
        self._handles: dict[ModelRef, ModelHandle] = {}

    def remember(
        self,
        handle: ModelHandle,
        *,
        provider: str,
        model_id: str | None = None,
    ) -> ModelRef:
        ref = ModelRef(
            provider=provider,
            model_id=model_id or self.model_id(handle),
        )
        self._handles.setdefault(ref, handle)
        return ref

    def resolve(self, ref: ModelRef) -> ModelHandle:
        try:
            return self._handles[ref]
        except KeyError as exc:
            raise KeyError(f"No runtime handle registered for {ref}") from exc

    @staticmethod
    def model_id(handle: ModelHandle) -> str:
        module = getattr(handle, "__module__", None) or type(handle).__module__
        qualname = getattr(handle, "__qualname__", None) or getattr(
            handle, "__name__", None
        )
        if qualname is None:
            return f"{module}.{type(handle).__qualname__}"
        return f"{module}.{qualname}"

    # -- payload ----------------------------------------------------------
    def materialize(
        self, container: ModelHandle, data: ModelData, *, strict: bool = False
    ) -> Any:
        return self._adapter(container).validate_python(data, strict=strict)

    def serialize(self, model: object) -> ModelData:
        return self._adapter(type(model)).dump_python(
            model, mode="python", by_alias=True
        )

    def validate(
        self, container: ModelHandle, data: ModelData, *, strict: bool = False
    ) -> ModelData:
        return self.serialize(self.materialize(container, data, strict=strict))

    def _adapter(self, container: ModelHandle) -> TypeAdapter[Any]:
        adapter = self._adapters.get(container)
        if adapter is None:
            adapter = TypeAdapter(container)
            self._adapters[container] = adapter
        return adapter

    # -- reflection -------------------------------------------------------
    def identify(self, model_cls: ModelHandle) -> bool:
        return isinstance(model_cls, type) and issubclass(model_cls, BaseModel)

    def can_handle(
        self,
        container: Any,
        *,
        fields: frozenset[str] | None = None,
    ) -> bool:
        if not (isinstance(container, type) and issubclass(container, BaseModel)):
            return False
        if fields is None:
            return True
        return any(
            fields <= set(model.model_fields)
            for model in self._reachable_models(container)
        )

    def _reachable_models(self, container: type[BaseModel]) -> list[type[BaseModel]]:
        found: list[type[BaseModel]] = [container]
        seen = {id(container)}
        stack = [container]
        while stack:
            current = stack.pop()
            for name in current.model_fields:
                annotation = current.model_fields[name].annotation
                for nested in self._iter_models(annotation):
                    if id(nested) in seen:
                        continue
                    seen.add(id(nested))
                    found.append(nested)
                    stack.append(nested)
        return found

    def resolve_model(self, annotation: Any) -> ModelHandle | None:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return annotation
        origin = getattr(annotation, "__origin__", None)
        args = getattr(annotation, "__args__", ())
        if origin is list and args:
            return self.resolve_model(args[0])
        for arg in args:
            resolved = self.resolve_model(arg)
            if resolved is not None:
                return resolved
        return None

    def field_model(
        self, parent_model: ModelHandle, field_name: str
    ) -> ModelHandle | None:
        field_info = parent_model.model_fields.get(field_name)
        if field_info is None:
            return None
        return self.resolve_model(field_info.annotation)

    def references(
        self,
        model_cls: ModelHandle,
        *,
        provider: str,
        codec: ModelCodec,
    ) -> frozenset[ModelVersionKey]:
        found: set[ModelVersionKey] = set()
        self._collect_references(
            model_cls, found, set(), provider=provider, codec=codec
        )
        return frozenset(found)

    def _collect_references(
        self,
        model_cls: ModelHandle,
        found: set[ModelVersionKey],
        seen: set[int],
        *,
        provider: str,
        codec: ModelCodec,
    ) -> None:
        if not self.identify(model_cls):
            return
        if id(model_cls) in seen:
            return
        seen.add(id(model_cls))
        for name in model_cls.model_fields:
            annotation = model_cls.model_fields[name].annotation
            for nested in self._iter_models(annotation):
                if nested is model_cls:
                    continue
                fields = self.describe_fields(nested, provider=provider, codec=codec)
                kind = codec.kind(fields)
                if not kind:
                    continue
                try:
                    version = codec.of(codec.version(fields))
                except (TypeError, ValueError):
                    continue
                found.add((kind, version))
                self._collect_references(
                    nested,
                    found,
                    seen,
                    provider=provider,
                    codec=codec,
                )

    def _iter_models(self, annotation: Any) -> list[ModelHandle]:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return [annotation]
        models: list[ModelHandle] = []
        for arg in getattr(annotation, "__args__", ()):
            models.extend(self._iter_models(arg))
        return models

    def describe_fields(
        self,
        model_cls: ModelHandle,
        *,
        provider: str,
        codec: ModelCodec,
    ) -> dict[str, FieldDescriptor]:
        descriptors = {
            name: FieldDescriptor(
                name=name,
                type_ref=self.type_ref(
                    field.annotation, provider=provider, codec=codec
                ),
                annotation=field.annotation,
                required=field.is_required(),
                default=(
                    NO_DEFAULT
                    if field.default is PydanticUndefined
                    else default_canonicalizer().encode(field.default)
                ),
            )
            for name, field in model_cls.model_fields.items()
        }
        for name, field_info in model_cls.model_fields.items():
            descriptors[name] = replace(
                descriptors[name],
                references=self._field_references(
                    model_cls,
                    field_info.annotation,
                    provider=provider,
                    codec=codec,
                ),
            )
        return descriptors

    def _field_references(
        self,
        model_cls: ModelHandle,
        annotation: Any,
        *,
        provider: str,
        codec: ModelCodec,
    ) -> tuple[ModelVersionKey, ...]:
        found: set[ModelVersionKey] = set()
        for nested in self._iter_models(annotation):
            if nested is model_cls:
                continue
            fields = self.describe_fields(nested, provider=provider, codec=codec)
            kind = codec.kind(fields)
            if not kind:
                continue
            try:
                found.add((kind, codec.of(codec.version(fields))))
            except (TypeError, ValueError):
                continue
            found.update(self.references(nested, provider=provider, codec=codec))
        return tuple(sorted(found, key=lambda item: (item[0], str(item[1]))))

    def type_ref(
        self,
        annotation: Any,
        *,
        provider: str,
        codec: ModelCodec,
    ) -> TypeRef:
        return annotation_type_ref(
            annotation,
            resolve_model=self.resolve_model,
            model_ref=lambda handle: self.remember(handle, provider=provider),
            version=lambda handle: codec.version(
                self.describe_fields(handle, provider=provider, codec=codec)
            ),
        )

    def materialize_model(
        self,
        diff: Diffable[VersionValue],
        *,
        codec: ModelCodec,
    ) -> ModelHandle:
        anchor = self.resolve(diff.source.descriptor.ref)
        version = diff.target.version[1]
        fields: dict[str, Any] = {codec.version_property: (str, str(version))}
        for name, field_info in anchor.model_fields.items():
            if name == codec.version_property or name in diff.removed_fields:
                continue
            fields[name] = (field_info.annotation, field_info)
        for name in diff.added_fields:
            if name in fields:
                continue
            info = diff.added_field_info.get(name, {})
            annotation = info.get("type") or Any
            default = info.get("default")
            if info.get("required"):
                fields[name] = (annotation, ...)
            elif default is not None:
                fields[name] = (annotation, default)
            else:
                fields[name] = (annotation, None)
        return create_model(
            f"{anchor.__name__}V{str(version).replace('.', '_')}",
            **fields,
        )


__all__ = ["ModelRuntime", "PythonModelRuntime"]
