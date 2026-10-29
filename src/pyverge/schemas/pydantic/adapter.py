from __future__ import annotations

from typing import Any

from pyverge.core.types import ModelData, ModelHandle, VersionValue
from pyverge.schemas.base import AbstractModelAdapter
from pyverge.schemas.codec import ModelCodec
from pyverge.schemas.runtime import ModelRuntime
from pyverge.versioning import Diffable, FieldDescriptor, NodeId


class PydanticModelAdapter(AbstractModelAdapter):
    """Pydantic provider adapter backed by a model runtime."""

    provider = "pydantic"

    def __init__(
        self,
        codec: ModelCodec,
        runtime: ModelRuntime | None = None,
    ) -> None:
        super().__init__(codec, runtime)

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
        return self.runtime.instantiate(container, data)

    def dump(self, model: object) -> ModelData:
        return self.runtime.serialize(model)

    def finalize(
        self, target_model: ModelHandle, data: dict[str, Any]
    ) -> dict[str, Any]:
        return self.runtime.validate(target_model, data)

    def validate(
        self,
        data: dict[str, Any],
        container: ModelHandle,
        *,
        strict: bool = False,
    ) -> dict[str, Any]:
        return self.runtime.validate(container, data, strict=strict)

    def resolve_model(self, annotation: Any) -> ModelHandle | None:
        return self.runtime.resolve_model(annotation)

    def field_model(
        self, parent_model: ModelHandle, field_name: str
    ) -> ModelHandle | None:
        return self.runtime.field_model(parent_model, field_name)

    def references(self, model_cls: ModelHandle) -> frozenset[NodeId]:
        return self.runtime.references(
            model_cls, provider=self.provider, codec=self.model_codec
        )

    def describe_fields(self, model_cls: ModelHandle) -> dict[str, FieldDescriptor]:
        return self.runtime.describe_fields(
            model_cls, provider=self.provider, codec=self.model_codec
        )

    def _materialize_model(self, diff: Diffable[VersionValue]) -> ModelHandle:
        return self.runtime.materialize_model(diff, codec=self.model_codec)


__all__ = ["PydanticModelAdapter"]
