from __future__ import annotations

import logging
from dataclasses import dataclass, replace
from typing import Any, Self, cast

from pydantic import BaseModel, create_model
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from pyverge.core.types import (
    ModelData,
    ModelHandle,
    ModelVersionKey,
    VersionValue,
)
from pyverge.schemas.base import AbstractModelAdapter
from pyverge.schemas.diff import FieldDescriptor, SchemaDiffer
from pyverge.versioning import (
    NO_DEFAULT,
    Comparable,
    Diff,
    Diffable,
    DiffOrigin,
    Versionable,
    VersionKey,
    VersionNode,
)

logger = logging.getLogger(__name__)


class PydanticModelAdapter(AbstractModelAdapter):
    provider = "pydantic"

    def _field_default(self, model_cls: ModelHandle, name: str) -> str:
        field_info: FieldInfo | None = model_cls.model_fields.get(name)
        if field_info is None:
            return ""

        default = field_info.default
        if default is PydanticUndefined:
            return ""

        return default if isinstance(default, str) else str(default)

    def version(self, model_cls: ModelHandle) -> str:
        return self._field_default(model_cls, self._version_property)

    def kind(self, model_cls: ModelHandle) -> str:
        return self._field_default(model_cls, self._kind_property)

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
        for model in self._reachable_models(container):
            if fields <= set(model.model_fields):
                return True
        return False

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

    def instantiate(self, container: ModelHandle, data: ModelData) -> Any:
        return container.model_validate(data)

    def dump(self, model: object) -> ModelData:
        if not isinstance(model, BaseModel):
            raise TypeError(
                f"Cannot serialize {type(model).__name__}: expected a Pydantic model"
            )
        return model.model_dump(by_alias=True)

    def finalize(
        self, target_model: ModelHandle, data: dict[str, Any]
    ) -> dict[str, Any]:
        result = dict(data)
        for field_name, field_info in target_model.model_fields.items():
            value = result.get(field_name)
            if value is None and not self._is_optional(field_info.annotation):
                default = None
                if field_info.default is not PydanticUndefined:
                    default = field_info.default
                elif field_info.default_factory is not None:
                    default = field_info.default_factory()
                output_key = (
                    field_info.serialization_alias or field_info.alias or field_name
                )
                result[output_key] = default

        return target_model.model_validate(result).model_dump(by_alias=True)

    def validate(
        self,
        data: dict[str, Any],
        container: ModelHandle,
        *,
        strict: bool = False,
    ) -> dict[str, Any]:
        if strict:
            return container.model_validate(data, strict=True).model_dump(by_alias=True)
        return container.model_validate(data).model_dump(by_alias=True)

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
                kind = self.kind(nested)
                if not kind:
                    continue
                try:
                    version = self.of(self.version(nested))
                except (TypeError, ValueError):
                    continue
                found.add((kind, version))
                self._collect_references(nested, found, seen)

    def _iter_models(self, annotation: Any) -> list[ModelHandle]:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return [annotation]

        models: list[ModelHandle] = []
        for arg in getattr(annotation, "__args__", ()):
            models.extend(self._iter_models(arg))
        return models

    def describe_fields(self, model_cls: ModelHandle) -> dict[str, FieldDescriptor]:
        descriptors = _describe_fields(model_cls)
        for name, field_info in model_cls.model_fields.items():
            references = self._field_references(model_cls, field_info.annotation)
            descriptors[name] = replace(descriptors[name], references=references)
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
            _model=model_cls,
            _value=self.of(version or self.version(model_cls)),
            _kind=kind or self.kind(model_cls),
            descriptor=self.model_descriptor(model_cls),
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
        return PydanticDiff.from_pair(
            source,
            cast("Versionable[VersionValue]", target),
        )

    @staticmethod
    def _is_optional(annotation: Any) -> bool:
        if annotation is None or annotation is type(None):
            return True
        origin = getattr(annotation, "__origin__", None)
        args = getattr(annotation, "__args__", ())
        if origin is not None and type(None) in args:
            return True
        return False

    def materialize_model(
        self,
        diff: Diffable[VersionValue],
    ) -> ModelHandle:
        anchor = diff.source.model
        version = diff.target.version[1]
        fields: dict[str, Any] = {}
        fields[self._version_property] = (str, str(version))
        for name, field_info in anchor.model_fields.items():
            if name == self._version_property or name in diff.removed_fields:
                continue
            fields[name] = (field_info.annotation, field_info)
        for name in diff.added_fields:
            if name in fields:
                continue
            info = diff.added_field_info.get(name, {})
            annotation = info.get("type")
            if annotation is None:
                annotation = Any
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


@dataclass(frozen=True)
class PydanticDiff(Diff[VersionValue]):
    """Differences between two Pydantic model versions.

    Computed eagerly from two Pydantic model classes. No migration logic —
    callers query the diff to decide what to do; rendering is a separate
    service.
    """

    @staticmethod
    def _diff_fields(source: FieldInfo, target: FieldInfo) -> dict[str, Any]:
        changes: dict[str, Any] = {}

        if source.annotation != target.annotation:
            changes["type_changed"] = {
                "from": source.annotation,
                "to": target.annotation,
            }

        from_req = source.is_required()
        to_req = target.is_required()
        if from_req != to_req:
            changes["required_changed"] = {"from": from_req, "to": to_req}

        from_def = source.default
        to_def = target.default
        if from_def != to_def and not (
            from_def is PydanticUndefined and to_def is PydanticUndefined
        ):
            if from_def is not PydanticUndefined and to_def is not PydanticUndefined:
                changes["default_changed"] = {"from": from_def, "to": to_def}
            elif from_def is PydanticUndefined:
                changes["default_added"] = to_def
            else:
                changes["default_removed"] = from_def

        return changes

    @classmethod
    def from_pair(
        cls: type[Self],
        source: Versionable[VersionValue],
        target: Versionable[VersionValue],
    ) -> Self:
        if source.strategy != target.strategy:
            raise ValueError(
                f"Cannot create diff across strategies: "
                f"{source.strategy.__name__} != {target.strategy.__name__}"
            )

        if source.kind != target.kind:
            raise ValueError(
                f"Cannot create diff across kinds: {source.kind} != {target.kind}"
            )

        return cls(
            source=source,
            target=target,
            fields=SchemaDiffer().fields(
                source.model,
                target.model,
                _describe_fields,
            ),
            origin=DiffOrigin.SCHEMA,
        )


def _describe_fields(model_cls: ModelHandle) -> dict[str, FieldDescriptor]:
    return {
        name: FieldDescriptor(
            name=name,
            annotation=field.annotation,
            required=field.is_required(),
            default=(
                NO_DEFAULT if field.default is PydanticUndefined else field.default
            ),
        )
        for name, field in model_cls.model_fields.items()
    }
