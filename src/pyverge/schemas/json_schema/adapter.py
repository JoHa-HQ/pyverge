from __future__ import annotations

import json
from typing import Any

from datamodel_code_generator import InputFileType, generate
from datamodel_code_generator.enums import DataModelType
from datamodel_code_generator.format import Formatter
from pydantic import BaseModel

from pyverge.core.types import ModelData, ModelHandle, ModelVersionKey, VersionValue
from pyverge.schemas.base import AbstractModelAdapter
from pyverge.schemas.codec import ModelCodec
from pyverge.versioning import Diffable, FieldDescriptor


class JsonSchemaModelAdapter(AbstractModelAdapter[VersionValue]):
    """Adapter for JSON Schema documents, delegated through Pydantic."""

    provider = "json_schema"

    def __init__(self, codec: ModelCodec) -> None:
        super().__init__(codec)
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

    def identify(self, model_cls: ModelHandle) -> bool:
        return self.model_codec.identify(model_cls)

    def can_handle(
        self,
        container: Any,
        *,
        fields: frozenset[str] | None = None,
    ) -> bool:
        return self.model_codec.can_handle(container, fields=fields)

    def instantiate(self, container: ModelHandle, data: ModelData) -> Any:
        return self.model_codec.materialize(self._model(container), data)

    def dump(self, model: object) -> ModelData:
        return self.model_codec.dump(model)

    def finalize(
        self, target_model: ModelHandle, data: dict[str, Any]
    ) -> dict[str, Any]:
        return self.model_codec.finalize(self._model(target_model), data)

    def validate(
        self,
        data: dict[str, Any],
        container: ModelHandle,
        *,
        strict: bool = False,
    ) -> dict[str, Any]:
        return self.model_codec.validate(self._model(container), data, strict=strict)

    def resolve_model(self, annotation: Any) -> ModelHandle | None:
        return self.model_codec.resolve_model(annotation)

    def field_model(
        self, parent_model: ModelHandle, field_name: str
    ) -> ModelHandle | None:
        return self.model_codec.field_model(self._model(parent_model), field_name)

    def references(self, model_cls: ModelHandle) -> frozenset[ModelVersionKey]:
        return self.model_codec.references(self._model(model_cls))

    def describe_fields(self, model_cls: ModelHandle) -> dict[str, FieldDescriptor]:
        return self.model_codec.describe_fields(
            self._model(model_cls), provider=self.provider
        )

    def versionable(
        self,
        model_cls: ModelHandle | dict[str, Any],
        *,
        kind: str | None = None,
        version: str | None = None,
    ):
        return super().versionable(self._model(model_cls), kind=kind, version=version)

    def materialize_model(self, diff: Diffable[VersionValue]) -> ModelHandle:
        return self.model_codec.materialize_model(diff)


__all__ = ["JsonSchemaModelAdapter"]
