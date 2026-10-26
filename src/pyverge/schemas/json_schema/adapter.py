from __future__ import annotations

import json
from typing import Any

from datamodel_code_generator import InputFileType, generate
from datamodel_code_generator.enums import DataModelType
from datamodel_code_generator.format import Formatter
from pydantic import BaseModel

from pyverge.core.types import (
    ModelData,
    ModelHandle,
    ModelVersionKey,
    VersionValue,
)
from pyverge.schemas.base import AbstractModelAdapter
from pyverge.schemas.diff import FieldDescriptor
from pyverge.schemas.pydantic.adapter import PydanticModelAdapter
from pyverge.versioning import (
    Comparable,
    Diff,
    Diffable,
    Versionable,
    VersionKey,
    VersionNode,
)


class JsonSchemaModelAdapter(AbstractModelAdapter):
    """Adapter for JSON Schema documents, delegated through Pydantic."""

    provider = "json_schema"

    def __init__(
        self,
        version_property: str = "version",
        kind_property: str = "kind",
    ) -> None:
        super().__init__(version_property, kind_property)
        self._pydantic = PydanticModelAdapter(version_property, kind_property)
        self._cache: dict[str, ModelHandle] = {}

    def to_pydantic(
        self, document: dict[str, Any], *, class_name: str = "Model"
    ) -> ModelHandle:
        key = json.dumps(document, sort_keys=True)
        if key not in self._cache:
            source = generate(
                json.dumps(document),
                input_file_type=InputFileType.JsonSchema,
                class_name=class_name,
                output_model_type=DataModelType.PydanticV2BaseModel,
                formatters=[Formatter.BUILTIN],
            )
            namespace: dict[str, Any] = {}
            exec(str(source), namespace)
            self._rebuild(namespace)
            self._cache[key] = namespace[class_name]
        return self._cache[key]

    @staticmethod
    def _rebuild(namespace: dict[str, Any]) -> None:
        for obj in list(namespace.values()):
            if isinstance(obj, type) and issubclass(obj, BaseModel):
                try:
                    obj.model_rebuild(_types_namespace=namespace)
                except Exception:
                    continue

    def _model(self, model_cls: ModelHandle | dict[str, Any]) -> ModelHandle:
        return self.to_pydantic(model_cls) if isinstance(model_cls, dict) else model_cls

    def version(self, model_cls: ModelHandle) -> str:
        return self._pydantic.version(model_cls)

    def kind(self, model_cls: ModelHandle) -> str:
        return self._pydantic.kind(model_cls)

    def identify(self, model_cls: ModelHandle) -> bool:
        return self._pydantic.identify(model_cls)

    def can_handle(
        self,
        container: Any,
        *,
        fields: frozenset[str] | None = None,
    ) -> bool:
        return self._pydantic.can_handle(container, fields=fields)

    def instantiate(self, container: ModelHandle, data: ModelData) -> Any:
        return self._pydantic.instantiate(self._model(container), data)

    def dump(self, model: object) -> ModelData:
        return self._pydantic.dump(model)

    def finalize(
        self, target_model: ModelHandle, data: dict[str, Any]
    ) -> dict[str, Any]:
        return self._pydantic.finalize(self._model(target_model), data)

    def validate(
        self,
        data: dict[str, Any],
        container: ModelHandle,
        *,
        strict: bool = False,
    ) -> dict[str, Any]:
        return self._pydantic.validate(data, self._model(container), strict=strict)

    def resolve_model(self, annotation: Any) -> ModelHandle | None:
        return self._pydantic.resolve_model(annotation)

    def field_model(
        self, parent_model: ModelHandle, field_name: str
    ) -> ModelHandle | None:
        return self._pydantic.field_model(self._model(parent_model), field_name)

    def fields(self, model_cls: ModelHandle) -> frozenset[str]:
        return self._pydantic.fields(self._model(model_cls))

    def references(self, model_cls: ModelHandle) -> frozenset[ModelVersionKey]:
        return self._pydantic.references(self._model(model_cls))

    def describe_fields(self, model_cls: ModelHandle) -> dict[str, FieldDescriptor]:
        return self._pydantic.describe_fields(self._model(model_cls))

    def versionable(
        self,
        model_cls: ModelHandle | dict[str, Any],
        *,
        kind: str | None = None,
        version: str | None = None,
    ) -> VersionNode[VersionValue]:
        resolved = self._model(model_cls)
        return VersionNode[VersionValue](
            _model=resolved,
            _value=self.of(version or self.version(resolved)),
            _kind=kind or self.kind(resolved),
            descriptor=self.model_descriptor(resolved),
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
        return self._pydantic.diff(source, target)

    def materialize_model(self, diff: Diffable[VersionValue]) -> ModelHandle:
        return self._pydantic.materialize_model(diff)


__all__ = ["JsonSchemaModelAdapter"]
