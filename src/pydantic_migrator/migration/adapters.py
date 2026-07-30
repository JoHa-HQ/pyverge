"""Provider-specific model adapters.

A :class:`ModelAdapter` is the only place allowed to know how a model
class encodes its ``version`` and ``kind``.  The rest of the migration
machinery works with :class:`Versionable` objects and never touches
provider-specific introspection APIs directly.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined


@runtime_checkable
class ModelAdapter(Protocol):
    """Provider-specific model operations.

    Implementations are provided for each supported model provider
    (Pydantic, attrs, dataclasses, MessagePack, etc.).  The migration
    engine and registry remain provider-agnostic.
    """

    def version(self, model_cls: type[Any]) -> str: ...
    def kind(self, model_cls: type[Any]) -> str: ...
    def finalize(
        self, target_model: type[Any], data: dict[str, Any]
    ) -> dict[str, Any]: ...


class PydanticModelAdapter:
    """Adapter for Pydantic ``BaseModel`` subclasses."""

    def __init__(
        self,
        version_property: str = "version",
        kind_property: str = "kind",
    ) -> None:
        self._version_property = version_property
        self._kind_property = kind_property

    def _field_default(self, model_cls: type[BaseModel], name: str) -> str:
        """Return the field's default value.

        Follows the idiomatic Pydantic pattern of declaring the value as a
        default: ``version: Literal["1.0.0"] = "1.0.0"``.  Required fields
        without a default are reported as an empty string so the caller can
        decide how to handle them.
        """
        field_info: FieldInfo | None = model_cls.model_fields.get(name)
        if field_info is None:
            return ""

        default = field_info.default
        if default is PydanticUndefined:
            return ""

        return default if isinstance(default, str) else str(default)

    def version(self, model_cls: type[BaseModel]) -> str:
        return self._field_default(model_cls, self._version_property)

    def kind(self, model_cls: type[BaseModel]) -> str:
        return self._field_default(model_cls, self._kind_property)

    def finalize(
        self, target_model: type[BaseModel], data: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply target-model defaults and validate/serialize the model."""
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

    @staticmethod
    def _is_optional(annotation: Any) -> bool:
        """Return ``True`` when *annotation* accepts ``None``."""
        if annotation is None or annotation is type(None):
            return True
        origin = getattr(annotation, "__origin__", None)
        args = getattr(annotation, "__args__", ())
        if origin is not None and type(None) in args:
            return True
        return False
