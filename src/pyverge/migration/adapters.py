"""Provider-specific model adapters.

A :class:`ModelAdapter` is the only place allowed to know how a model
class encodes its ``version`` and ``kind``.  The rest of the migration
machinery works with :class:`Versionable` objects and never touches
provider-specific introspection APIs directly.
"""

from __future__ import annotations

from typing import Any, cast

from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from .types import Versionable, VersionValue, VModel
from .versioning import VersionNode


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

    def validate(
        self,
        data: dict[str, Any],
        container: type[BaseModel],
        *,
        strict: bool = False,
    ) -> dict[str, Any]:
        """Validate *data* against *container* and return the dumped payload."""
        if strict:
            return container.model_validate(data, strict=True).model_dump(by_alias=True)
        return container.model_validate(data).model_dump(by_alias=True)

    def resolve_model(self, annotation: Any) -> type[BaseModel] | None:
        """Return the first concrete ``BaseModel`` subclass inside *annotation*.

        Handles direct types, ``Optional[T]``, ``list[T]``, and ``Union`` forms.
        """
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
        self, parent_model: type[BaseModel], field_name: str
    ) -> type[BaseModel] | None:
        """Return the model class for *field_name* on *parent_model*, if any."""
        field_info = parent_model.model_fields.get(field_name)
        if field_info is None:
            return None
        return self.resolve_model(field_info.annotation)

    def versionable(self, model_cls: type[VModel]) -> Versionable[VersionValue, VModel]:
        """Build a ``VersionNode`` wrapping *model_cls* using its encoded metadata."""
        return cast(
            Versionable[VersionValue, VModel],
            VersionNode[VersionValue, VModel](
                _model=model_cls,
                _value=cast(VersionValue, VersionNode.of(self.version(model_cls))),
                _kind=self.kind(model_cls),
            ),
        )

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
