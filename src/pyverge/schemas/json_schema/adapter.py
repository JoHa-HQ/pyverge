from __future__ import annotations

import hashlib
import json
import re
from typing import Any, get_args

from datamodel_code_generator import InputFileType, generate
from datamodel_code_generator.enums import DataModelType
from datamodel_code_generator.format import Formatter
from pydantic import BaseModel

from pyverge.core.types import ModelData, ModelHandle, VersionValue
from pyverge.schemas.base import AbstractModelAdapter
from pyverge.schemas.codec import ModelCodec
from pyverge.schemas.runtime import ModelRuntime
from pyverge.versioning import Diffable, FieldDescriptor, NodeId


class JsonSchemaModelAdapter(AbstractModelAdapter):
    """Adapter for JSON Schema documents, delegated through Pydantic."""

    provider = "json_schema"

    def __init__(
        self,
        codec: ModelCodec,
        runtime: ModelRuntime | None = None,
    ) -> None:
        super().__init__(codec, runtime)
        self._cache: dict[tuple[str, str], ModelHandle] = {}
        self._model_ids: dict[ModelHandle, str] = {}

    def to_pydantic(
        self, document: dict[str, Any], *, class_name: str = "Model"
    ) -> ModelHandle:
        if not class_name or not class_name.isidentifier():
            raise ValueError(f"Invalid class_name: {class_name!r}")

        document_json = json.dumps(document, sort_keys=True)
        key = (class_name, document_json)
        if key not in self._cache:
            source = generate(
                document_json,
                input_file_type=InputFileType.JsonSchema,
                class_name=class_name,
                output_model_type=DataModelType.PydanticV2BaseModel,
                formatters=[Formatter.BUILTIN],
                use_annotated=True,
                allow_remote_refs=False,
            )
            namespace: dict[str, Any] = {}
            exec(str(source), namespace)
            self._rebuild(namespace)
            digest = hashlib.sha256(document_json.encode()).hexdigest()[:12]
            generated_module = f"pyverge.generated.{digest}"
            for obj in namespace.values():
                if isinstance(obj, type) and issubclass(obj, BaseModel):
                    obj.__module__ = generated_module
                    self._model_ids[obj] = f"{obj.__name__}@{digest}"
            self._cache[key] = self._root_model(namespace, class_name)
        return self._cache[key]

    def model_id(self, handle: ModelHandle) -> str:
        return self._model_ids.get(handle, super().model_id(handle))

    @classmethod
    def _root_model(cls, namespace: dict[str, Any], class_name: str) -> ModelHandle:
        models = [
            obj
            for obj in namespace.values()
            if isinstance(obj, type)
            and issubclass(obj, BaseModel)
            and obj is not BaseModel
        ]
        referenced = {
            nested
            for model in models
            for field in model.model_fields.values()
            for nested in cls._iter_models(field.annotation)
        }
        roots = [model for model in models if model not in referenced] or models

        exact = next((model for model in roots if model.__name__ == class_name), None)
        if exact is not None:
            return exact

        normalized = cls._normalize_name(class_name)
        for model in roots:
            if cls._normalize_name(model.__name__) == normalized:
                return model

        if len(roots) == 1:
            return roots[0]

        candidates = sorted(model.__name__ for model in roots)
        raise ValueError(
            f"Generated root model for class_name={class_name!r} not found; "
            f"candidates={candidates}"
        )

    @classmethod
    def _iter_models(cls, annotation: Any) -> list[type[BaseModel]]:
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return [annotation]
        models: list[type[BaseModel]] = []
        for arg in get_args(annotation):
            models.extend(cls._iter_models(arg))
        return models

    @staticmethod
    def _normalize_name(name: str) -> str:
        return re.sub(r"[^0-9A-Za-z]", "", name).casefold()

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
        return self.runtime.identify(model_cls)

    def can_handle(
        self,
        container: Any,
        *,
        fields: frozenset[str] | None = None,
    ) -> bool:
        return self.runtime.can_handle(container, fields=fields)

    def instantiate(self, container: ModelHandle, data: ModelData) -> Any:
        return self.runtime.instantiate(self._model(container), data)

    def dump(self, model: object) -> ModelData:
        return self.runtime.serialize(model)

    def finalize(
        self, target_model: ModelHandle, data: dict[str, Any]
    ) -> dict[str, Any]:
        return self.runtime.validate(self._model(target_model), data)

    def validate(
        self,
        data: dict[str, Any],
        container: ModelHandle,
        *,
        strict: bool = False,
    ) -> dict[str, Any]:
        return self.runtime.validate(self._model(container), data, strict=strict)

    def resolve_model(self, annotation: Any) -> ModelHandle | None:
        return self.runtime.resolve_model(annotation)

    def field_model(
        self, parent_model: ModelHandle, field_name: str
    ) -> ModelHandle | None:
        return self.runtime.field_model(self._model(parent_model), field_name)

    def references(self, model_cls: ModelHandle) -> frozenset[NodeId]:
        return self.runtime.references(
            self._model(model_cls),
            provider=self.provider,
            codec=self.model_codec,
        )

    def describe_fields(self, model_cls: ModelHandle) -> dict[str, FieldDescriptor]:
        return self.runtime.describe_fields(
            self._model(model_cls),
            provider=self.provider,
            codec=self.model_codec,
        )

    def versionable(
        self,
        model_cls: ModelHandle | dict[str, Any],
        *,
        kind: str | None = None,
        version: str | None = None,
    ):
        return super().versionable(self._model(model_cls), kind=kind, version=version)

    def _materialize_model(self, diff: Diffable[VersionValue]) -> ModelHandle:
        return self.runtime.materialize_model(diff, codec=self.model_codec)


__all__ = ["JsonSchemaModelAdapter"]
