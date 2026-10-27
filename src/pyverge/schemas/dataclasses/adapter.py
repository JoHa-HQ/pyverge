from __future__ import annotations

import dataclasses
import types
from collections.abc import Iterable, Mapping, Sequence
from typing import (
    Annotated,
    Any,
    Literal,
    Union,
    get_args,
    get_origin,
    get_type_hints,
)

from pyverge.core.types import (
    ModelData,
    ModelHandle,
    ModelVersionKey,
    VersionValue,
)
from pyverge.schemas.base import AbstractModelAdapter
from pyverge.schemas.codec import ModelCodec
from pyverge.versioning import (
    NO_DEFAULT,
    Diffable,
    FieldDescriptor,
    TypeKind,
    TypeRef,
    default_canonicalizer,
)

_MAPPING_ARG_COUNT = 2
_TUPLE_ELLIPSIS_ARGS = 2

_SIMPLE_TYPES: dict[Any, TypeKind] = {
    bool: TypeKind.BOOLEAN,
    int: TypeKind.INTEGER,
    float: TypeKind.NUMBER,
    str: TypeKind.STRING,
    bytes: TypeKind.BYTES,
}


class DataclassModelAdapter(AbstractModelAdapter[VersionValue]):
    """Model adapter for ordinary :mod:`dataclasses` classes.

    Dataclasses are the runtime container, but payload validation and
    coercion are delegated to Pydantic.  This keeps the richer validation
    surface (nested coercion, defaults, constraints, strict mode) available
    while the graph keeps an opaque stdlib handle.
    """

    provider = "dataclass"

    def __init__(
        self,
        codec: ModelCodec,
    ) -> None:
        super().__init__(codec)

    def identify(self, model_cls: ModelHandle) -> bool:
        return isinstance(model_cls, type) and dataclasses.is_dataclass(model_cls)

    def _hints(self, model_cls: ModelHandle) -> dict[str, Any]:
        try:
            return get_type_hints(model_cls)
        except (NameError, TypeError):
            return {field.name: field.type for field in dataclasses.fields(model_cls)}

    def can_handle(
        self,
        container: Any,
        *,
        fields: frozenset[str] | None = None,
    ) -> bool:
        if not (isinstance(container, type) and dataclasses.is_dataclass(container)):
            return False
        if fields is None:
            return True
        return any(
            fields <= {field.name for field in dataclasses.fields(model)}
            for model in self._reachable_models(container)
        )

    def _reachable_models(self, container: type[Any]) -> list[type[Any]]:
        found: list[type[Any]] = [container]
        seen = {id(container)}
        stack = [container]
        while stack:
            current = stack.pop()
            hints = self._hints(current)
            for field in dataclasses.fields(current):
                for nested in self._iter_models(hints.get(field.name, field.type)):
                    if id(nested) in seen:
                        continue
                    seen.add(id(nested))
                    found.append(nested)
                    stack.append(nested)
        return found

    def _iter_models(self, annotation: Any) -> list[ModelHandle]:
        if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
            return [annotation]
        models: list[ModelHandle] = []
        for arg in get_args(annotation):
            models.extend(self._iter_models(arg))
        return models

    def resolve_model(self, annotation: Any) -> ModelHandle | None:
        if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
            return annotation
        origin = get_origin(annotation)
        args = get_args(annotation)
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
        hints = self._hints(parent_model)
        for field in dataclasses.fields(parent_model):
            if field.name == field_name:
                return self.resolve_model(hints.get(field.name, field.type))
        return None

    def references(self, model_cls: ModelHandle) -> frozenset[ModelVersionKey]:
        found: set[ModelVersionKey] = set()
        self._collect_references(model_cls, found, set())
        return frozenset(found)

    def _collect_references(
        self,
        model_cls: ModelHandle,
        found: set[ModelVersionKey],
        seen: set[int],
    ) -> None:
        if not (isinstance(model_cls, type) and dataclasses.is_dataclass(model_cls)):
            return
        if id(model_cls) in seen:
            return
        seen.add(id(model_cls))
        hints = self._hints(model_cls)
        for field in dataclasses.fields(model_cls):
            for nested in self._iter_models(hints.get(field.name, field.type)):
                if nested is model_cls:
                    continue
                kind = self.kind(nested)
                if not kind:
                    continue
                try:
                    version = self.of(self.version(nested))
                except (TypeError, ValueError):
                    continue
                found.add((kind, version))
                self._collect_references(nested, found, seen)

    def instantiate(self, container: ModelHandle, data: ModelData) -> Any:
        return self.model_codec.materialize(container, data)

    def dump(self, model: object) -> ModelData:
        if not dataclasses.is_dataclass(model):
            raise TypeError(
                f"Cannot serialize {type(model).__name__}: expected a dataclass"
            )
        return self.model_codec.dump(model)

    def finalize(
        self, target_model: ModelHandle, data: dict[str, Any]
    ) -> dict[str, Any]:
        return self.model_codec.finalize(target_model, data)

    def validate(
        self,
        data: dict[str, Any],
        container: ModelHandle,
        *,
        strict: bool = False,
    ) -> dict[str, Any]:
        return self.model_codec.validate(container, data, strict=strict)

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
            return TypeRef.model(self.ref(resolved), version=version or None)

        if isinstance(annotation, type):
            return TypeRef.unknown(f"{annotation.__module__}.{annotation.__qualname__}")
        return TypeRef.unknown(str(annotation))

    def describe_fields(self, model_cls: ModelHandle) -> dict[str, FieldDescriptor]:
        hints = self._hints(model_cls)
        descriptors = {
            field.name: FieldDescriptor(
                name=field.name,
                type_ref=self.type_ref(hints.get(field.name, field.type)),
                annotation=hints.get(field.name, field.type),
                required=(
                    field.default is dataclasses.MISSING
                    and field.default_factory is dataclasses.MISSING
                ),
                default=(
                    default_canonicalizer().encode(field.default)
                    if field.default is not dataclasses.MISSING
                    else default_canonicalizer().encode(field.default_factory())
                    if field.default_factory is not dataclasses.MISSING
                    else NO_DEFAULT
                ),
            )
            for field in dataclasses.fields(model_cls)
        }
        for field in dataclasses.fields(model_cls):
            references = self._field_references(
                model_cls, hints.get(field.name, field.type)
            )
            descriptors[field.name] = dataclasses.replace(
                descriptors[field.name], references=references
            )
        return descriptors

    def _field_references(
        self, model_cls: ModelHandle, annotation: Any
    ) -> tuple[ModelVersionKey, ...]:
        found: set[ModelVersionKey] = set()
        for nested in self._iter_models(annotation):
            if nested is model_cls:
                continue
            kind = self.kind(nested)
            if not kind:
                continue
            try:
                found.add((kind, self.of(self.version(nested))))
            except (TypeError, ValueError):
                continue
            found.update(self.references(nested))
        return tuple(sorted(found, key=lambda item: (item[0], str(item[1]))))

    def materialize_model(self, diff: Diffable[VersionValue]) -> ModelHandle:
        anchor = self.model_codec.resolve(diff.source.descriptor.ref)
        version = diff.target.version[1]
        version_field = (
            self.version_property,
            str,
            dataclasses.field(default=str(version)),
        )
        fields: list[Any] = [version_field]
        for field in dataclasses.fields(anchor):
            if field.name in {self.version_property, *diff.removed_fields}:
                continue
            if field.default is not dataclasses.MISSING:
                fields.append(
                    (field.name, field.type, dataclasses.field(default=field.default))
                )
            elif field.default_factory is not dataclasses.MISSING:
                fields.append(
                    (
                        field.name,
                        field.type,
                        dataclasses.field(default_factory=field.default_factory),
                    )
                )
            else:
                fields.append((field.name, field.type))
        for name in diff.added_fields:
            info = diff.added_field_info.get(name, {})
            annotation = info.get("type", Any)
            default = info.get("default")
            if info.get("required"):
                fields.append((name, annotation))
            else:
                fields.append((name, annotation, dataclasses.field(default=default)))
        name = f"{anchor.__name__}V{str(version).replace('.', '_')}"
        return dataclasses.make_dataclass(name, fields, kw_only=True)
