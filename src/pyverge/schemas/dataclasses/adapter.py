from __future__ import annotations

import dataclasses
from typing import Any, cast, get_args, get_origin, get_type_hints

from pyverge.core.types import (
    ModelData,
    ModelHandle,
    ModelVersionKey,
    VersionValue,
)
from pyverge.schemas.base import AbstractModelAdapter
from pyverge.schemas.diff import FieldDescriptor, SchemaDiffer
from pyverge.versioning import (
    Comparable,
    Diff,
    Diffable,
    DiffOrigin,
    Versionable,
    VersionKey,
    VersionNode,
)


class DataclassModelAdapter(AbstractModelAdapter):
    """Model adapter for ordinary :mod:`dataclasses` classes."""

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

    def _coerce(self, annotation: Any, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
            if isinstance(value, annotation):
                return value
            return self.instantiate(annotation, cast(ModelData, value))
        origin = get_origin(annotation)
        args = get_args(annotation)
        if origin is list and args and isinstance(value, list):
            return [self._coerce(args[0], item) for item in value]
        if origin is not None and type(None) in args:
            for arg in args:
                if arg is type(None):
                    continue
                try:
                    return self._coerce(arg, value)
                except (TypeError, ValueError):
                    continue
        return value

    def instantiate(self, container: ModelHandle, data: ModelData) -> Any:
        values: dict[str, Any] = {}
        hints = self._hints(container)
        for field in dataclasses.fields(container):
            if not field.init:
                continue
            if field.name in data:
                values[field.name] = self._coerce(
                    hints.get(field.name, field.type), data[field.name]
                )
            elif field.default is not dataclasses.MISSING:
                values[field.name] = field.default
            elif field.default_factory is not dataclasses.MISSING:
                values[field.name] = field.default_factory()
            else:
                raise TypeError(
                    f"Missing required dataclass field '{field.name}' "
                    f"for {container.__name__}"
                )
        return container(**values)

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
        return self.dump(self.instantiate(container, data))

    def describe_fields(self, model_cls: ModelHandle) -> dict[str, FieldDescriptor]:
        hints = self._hints(model_cls)
        return {
            field.name: FieldDescriptor(
                name=field.name,
                annotation=hints.get(field.name, field.type),
                required=(
                    field.default is dataclasses.MISSING
                    and field.default_factory is dataclasses.MISSING
                ),
                default=(
                    field.default
                    if field.default is not dataclasses.MISSING
                    else field.default_factory()
                    if field.default_factory is not dataclasses.MISSING
                    else None
                ),
            )
            for field in dataclasses.fields(model_cls)
        }

    def versionable(
        self,
        model_cls: ModelHandle,
        *,
        kind: str | None = None,
        version: str | None = None,
    ) -> VersionNode[VersionValue]:
        return VersionNode[VersionValue](
            _model=model_cls,
            _value=self.of(version or self.version(model_cls)),
            _kind=kind or self.kind(model_cls),
            references=self.references(model_cls),
            fields=self.fields(model_cls),
            model_id=self.model_id(model_cls),
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

        return SchemaDiffer().diff(source, target, self.describe_fields)

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
        return dataclasses.make_dataclass(name, fields)
