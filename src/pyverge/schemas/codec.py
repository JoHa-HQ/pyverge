from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from typing import Any, cast

import pendulum
from pydantic import BaseModel, TypeAdapter, create_model
from pydantic_core import PydanticUndefined
from semver import Version

from pyverge.core.types import ModelData, ModelHandle, ModelVersionKey, VersionValue
from pyverge.schemas.type_projection import annotation_type_ref
from pyverge.versioning import (
    NO_DEFAULT,
    Diffable,
    FieldDescriptor,
    ModelRef,
    NoDefault,
    TypeRef,
    VersionKey,
    default_canonicalizer,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ModelCodec:
    """Shared identity, payload, and Pydantic reflection codec."""

    version_property: str = "version"
    kind_property: str = "kind"
    _adapters: dict[Any, TypeAdapter[Any]] = field(
        default_factory=dict, compare=False, repr=False
    )
    _handles: dict[ModelRef, ModelHandle] = field(
        default_factory=dict, compare=False, repr=False
    )

    # -- identity ---------------------------------------------------------
    def of(self, value: str | VersionValue) -> VersionValue:
        if isinstance(value, Version) or (
            isinstance(value, pendulum.Date)
            and not isinstance(value, pendulum.DateTime)
        ):
            return cast(VersionValue, value)

        if not isinstance(value, str):
            msg = f"Cannot parse version {value!r}: expected a string or VersionValue."
            raise TypeError(msg)

        try:
            return cast(VersionValue, Version.parse(value))
        except ValueError:
            logger.debug(f"Failed to parse semver: {value!r}")

        try:
            parsed = pendulum.parse(str(value), exact=True)
            if isinstance(parsed, pendulum.DateTime):
                parsed = parsed.date()
            if not isinstance(parsed, pendulum.Date):
                raise ValueError(f"Expected date, got {parsed!r}")
            return cast(VersionValue, parsed)
        except ValueError:
            logger.debug(f"Failed to parse date: {value!r}")

        msg = (
            f"Cannot parse version {value!r}. "
            "Expected semver (e.g. '1.0.0') or ISO date (e.g. '2024-06-01')."
        )
        raise ValueError(msg)

    def version(self, fields: Mapping[str, FieldDescriptor]) -> str:
        return self._default(fields, self.version_property)

    def kind(self, fields: Mapping[str, FieldDescriptor]) -> str:
        return self._default(fields, self.kind_property)

    def version_key(self, *, kind: str, version: str) -> VersionKey[VersionValue]:
        return VersionKey[VersionValue](_value=self.of(version), _kind=kind)

    def ref(self, handle: ModelHandle, *, provider: str) -> ModelRef:
        ref = ModelRef(provider=provider, model_id=self.model_id(handle))
        self._handles[ref] = handle
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

    @staticmethod
    def _default(fields: Mapping[str, FieldDescriptor], name: str) -> str:
        descriptor = fields.get(name)
        if descriptor is None or isinstance(descriptor.default, NoDefault):
            return ""
        default = descriptor.default
        return default if isinstance(default, str) else str(default)

    # -- payload ----------------------------------------------------------
    def materialize(
        self, container: ModelHandle, data: ModelData, *, strict: bool = False
    ) -> Any:
        return self._adapter(container).validate_python(data, strict=strict)

    def dump(self, model: object) -> ModelData:
        return self._adapter(type(model)).dump_python(
            model, mode="python", by_alias=True
        )

    def finalize(self, container: ModelHandle, data: ModelData) -> ModelData:
        return self.dump(self.materialize(container, data))

    def validate(
        self, container: ModelHandle, data: ModelData, *, strict: bool = False
    ) -> ModelData:
        return self.dump(self.materialize(container, data, strict=strict))

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
        self, model_cls: ModelHandle, *, provider: str
    ) -> frozenset[ModelVersionKey]:
        found: set[ModelVersionKey] = set()
        self._collect_references(model_cls, found, set(), provider=provider)
        return frozenset(found)

    def _collect_references(
        self,
        model_cls: ModelHandle,
        found: set[ModelVersionKey],
        seen: set[int],
        *,
        provider: str,
    ) -> None:
        if not (isinstance(model_cls, type) and issubclass(model_cls, BaseModel)):
            return
        if id(model_cls) in seen:
            return
        seen.add(id(model_cls))
        for name in model_cls.model_fields:
            annotation = model_cls.model_fields[name].annotation
            for nested in self._iter_models(annotation):
                if nested is model_cls:
                    continue
                kind = self.kind(self.describe_fields(nested, provider=provider))
                if not kind:
                    continue
                try:
                    version = self.of(
                        self.version(self.describe_fields(nested, provider=provider))
                    )
                except (TypeError, ValueError):
                    continue
                found.add((kind, version))
                self._collect_references(nested, found, seen, provider=provider)

    def _iter_models(self, annotation: Any) -> list[ModelHandle]:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return [annotation]
        models: list[ModelHandle] = []
        for arg in getattr(annotation, "__args__", ()):
            models.extend(self._iter_models(arg))
        return models

    def describe_fields(
        self, model_cls: ModelHandle, *, provider: str
    ) -> dict[str, FieldDescriptor]:
        descriptors = {
            name: FieldDescriptor(
                name=name,
                type_ref=self.type_ref(field.annotation, provider=provider),
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
                    model_cls, field_info.annotation, provider=provider
                ),
            )
        return descriptors

    def _field_references(
        self, model_cls: ModelHandle, annotation: Any, *, provider: str
    ) -> tuple[ModelVersionKey, ...]:
        found: set[ModelVersionKey] = set()
        for nested in self._iter_models(annotation):
            if nested is model_cls:
                continue
            fields = self.describe_fields(nested, provider=provider)
            kind = self.kind(fields)
            if not kind:
                continue
            try:
                found.add((kind, self.of(self.version(fields))))
            except (TypeError, ValueError):
                continue
            found.update(self.references(nested, provider=provider))
        return tuple(sorted(found, key=lambda item: (item[0], str(item[1]))))

    def type_ref(self, annotation: Any, *, provider: str) -> TypeRef:
        return annotation_type_ref(
            annotation,
            resolve_model=self.resolve_model,
            model_ref=lambda handle: self.ref(handle, provider=provider),
            version=lambda handle: self.version(
                self.describe_fields(handle, provider=provider)
            ),
        )

    def materialize_model(self, diff: Diffable[VersionValue]) -> ModelHandle:
        anchor = self.resolve(diff.source.descriptor.ref)
        version = diff.target.version[1]
        fields: dict[str, Any] = {self.version_property: (str, str(version))}
        for name, field_info in anchor.model_fields.items():
            if name == self.version_property or name in diff.removed_fields:
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


__all__ = ["ModelCodec"]
