from __future__ import annotations

from typing import Any

from pyverge.core.types import ModelData, ModelHandle, ModelVersionKey, VersionValue
from pyverge.schemas.base import AbstractModelAdapter
from pyverge.schemas.codec import ModelCodec
from pyverge.versioning import Diffable, FieldDescriptor


class PydanticModelAdapter(AbstractModelAdapter[VersionValue]):
    """Pydantic provider adapter backed by :class:`ModelCodec`."""

    provider = "pydantic"

    def __init__(self, codec: ModelCodec) -> None:
        super().__init__(codec)

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
        return self.model_codec.materialize(container, data)

    def dump(self, model: object) -> ModelData:
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

    def resolve_model(self, annotation: Any) -> ModelHandle | None:
        return self.model_codec.resolve_model(annotation)

    def field_model(
        self, parent_model: ModelHandle, field_name: str
    ) -> ModelHandle | None:
        return self.model_codec.field_model(parent_model, field_name)

    def references(self, model_cls: ModelHandle) -> frozenset[ModelVersionKey]:
        return self.model_codec.references(model_cls)

    def describe_fields(self, model_cls: ModelHandle) -> dict[str, FieldDescriptor]:
        return self.model_codec.describe_fields(model_cls, provider=self.provider)

    def materialize_model(self, diff: Diffable[VersionValue]) -> ModelHandle:
        return self.model_codec.materialize_model(diff)


__all__ = ["PydanticModelAdapter"]
