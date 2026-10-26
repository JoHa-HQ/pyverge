from __future__ import annotations

import dataclasses
import types
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

from pydantic import TypeAdapter

from pyverge.core.types import (
    ModelData,
    ModelHandle,
    ModelVersionKey,
    VersionValue,
)
from pyverge.schemas.base import AbstractModelAdapter
from pyverge.versioning import (
    NO_DEFAULT,
    Comparable,
    Diff,
    Diffable,
    DiffOrigin,
    FieldDescriptor,
    SchemaDiffer,
    Versionable,
    VersionKey,
    VersionNode,
    default_canonicalizer,
)

_MAPPING_ARG_COUNT = 2


class DataclassModelAdapter(AbstractModelAdapter):
    """Model adapter for ordinary :mod:`dataclasses` classes.

    Dataclasses are the runtime container, but payload validation and
    coercion are delegated to Pydantic.  This keeps the richer validation
    surface (nested coercion, defaults, constraints, strict mode) available
    while the graph keeps an opaque stdlib handle.
    """

    provider = "dataclass"

    def __init__(
        self,
        version_property: str = "version",
        kind_property: str = "kind",
    ) -> None:
        super().__init__(version_property, kind_property)
        self._adapters: dict[type[Any], TypeAdapter[Any]] = {}

    def _adapter(self, container: ModelHandle) -> TypeAdapter[Any]:
        adapter = self._adapters.get(container)
        if adapter is None:
            adapter = TypeAdapter(container)
            self._adapters[container] = adapter
        return adapter

    def _field_default(self, model_cls: ModelHandle, name: str) -> str:
        for field in dataclasses.fields(model_cls):
            if field.name != name:
                continue
            if field.default is not dataclasses.MISSING:
                return (
                    field.default
                    if isinstance(field.default, str)
                    else str(field.default)
                )
            if field.default_factory is not dataclasses.MISSING:
                return str(field.default_factory())
            return ""
        return ""

    def version(self, model_cls: ModelHandle) -> str:
        return self._field_default(model_cls, self._version_property)

    def kind(self, model_cls: ModelHandle) -> str:
        return self._field_default(model_cls, self._kind_property)

    def identify(self, model_cls: ModelHandle) -> bool:
        return isinstance(model_cls, type) and dataclasses.is_dataclass(model_cls)

    def fields(self, model_cls: ModelHandle) -> frozenset[str]:
        identity = {self._version_property, self._kind_property}
        return frozenset(
            field.name
            for field in dataclasses.fields(model_cls)
            if field.name not in identity
        )

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

    def _strict_validate(self, annotation: Any, value: Any) -> None:
        if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
            self._strict_dataclass(annotation, value)
            return

        origin = get_origin(annotation)
        args = get_args(annotation)

        if origin is Union or origin is types.UnionType:
            self._strict_union(args, value)
            return
        if origin is list and args and isinstance(value, list):
            for item in value:
                self._strict_validate(args[0], item)
            return
        if (
            origin is dict
            and len(args) == _MAPPING_ARG_COUNT
            and isinstance(value, dict)
        ):
            for key, item in value.items():
                self._strict_validate(args[0], key)
                self._strict_validate(args[1], item)
            return

        self._adapter(annotation).validate_python(value, strict=True)

    def _strict_dataclass(self, container: ModelHandle, value: Any) -> None:
        if isinstance(value, container):
            value = dataclasses.asdict(value)
        if not isinstance(value, dict):
            self._adapter(container).validate_python(value, strict=True)
            return

        hints = self._hints(container)
        for field in dataclasses.fields(container):
            if not field.init:
                continue
            if field.name in value:
                self._strict_validate(
                    hints.get(field.name, field.type), value[field.name]
                )
            elif (
                field.default is dataclasses.MISSING
                and field.default_factory is dataclasses.MISSING
            ):
                raise TypeError(
                    f"Missing required dataclass field '{field.name}' "
                    f"for {container.__name__}"
                )

    def _strict_union(self, args: tuple[Any, ...], value: Any) -> None:
        if value is None and type(None) in args:
            return
        errors: list[Exception] = []
        for arg in args:
            if arg is type(None):
                continue
            try:
                self._strict_validate(arg, value)
                return
            except Exception as exc:
                errors.append(exc)
        if errors:
            raise errors[-1]
        raise TypeError(f"Value {value!r} does not match {args!r}")

    def instantiate(self, container: ModelHandle, data: ModelData) -> Any:
        return self._adapter(container).validate_python(data)

    def dump(self, model: object) -> ModelData:
        if not dataclasses.is_dataclass(model):
            raise TypeError(
                f"Cannot serialize {type(model).__name__}: expected a dataclass"
            )
        return dataclasses.asdict(cast(Any, model))

    def finalize(
        self, target_model: ModelHandle, data: dict[str, Any]
    ) -> dict[str, Any]:
        return self.dump(self.instantiate(target_model, data))

    def validate(
        self,
        data: dict[str, Any],
        container: ModelHandle,
        *,
        strict: bool = False,
    ) -> dict[str, Any]:
        if strict:
            self._strict_validate(container, data)
        return self.dump(self.instantiate(container, data))

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
        return VersionKey[VersionValue](_value=self.of(version), _kind=kind)

    def diff(
        self,
        source: Versionable[VersionValue],
        target: Comparable[VersionValue],
    ) -> Diff[VersionValue]:
        if getattr(target, "model", None) is None:
            return Diff(
                source=source,
                target=target,
                fields={},
                origin=DiffOrigin.SCHEMA,
            )

        return SchemaDiffer().diff(source, target)

    def materialize_model(self, diff: Diffable[VersionValue]) -> ModelHandle:
        anchor = diff.source.model
        version = diff.target.version[1]
        version_field = (
            self._version_property,
            str,
            dataclasses.field(default=str(version)),
        )
        fields: list[Any] = [version_field]
        for field in dataclasses.fields(anchor):
            if field.name in {self._version_property, *diff.removed_fields}:
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
