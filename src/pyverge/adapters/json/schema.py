"""JSON Schema model adapter.

:class:`JsonSchemaModelAdapter` converts a JSON Schema document (a plain dict)
into a Pydantic model via ``datamodel-code-generator`` and registers that model
with the engine.  The adapter interface operates on ``type[BaseModel]`` only —
the same contract as :class:`PydanticModelAdapter` — so the engine never sees
JSON Schema semantics.
"""

from __future__ import annotations

import json
from typing import Any, cast

from datamodel_code_generator import InputFileType, generate
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from pyverge.adapters.base import BaseModelAdapter
from pyverge.migration.diff import Diff
from pyverge.migration.types import (
    Versionable,
    VersionValue,
    VModel,
    VSource_co,
    VTarget_co,
)
from pyverge.migration.versioning import VersionNode


class JsonSchemaModelAdapter(BaseModelAdapter):
    """Adapter for models defined as JSON Schema documents.

    Converts a schema document to a Pydantic model via
    ``datamodel-code-generator``; ``version``/``kind`` are read from the
    model's fields, mirroring :class:`PydanticModelAdapter`.
    """

    def __init__(
        self,
        version_property: str = "version",
        kind_property: str = "kind",
    ) -> None:
        super().__init__(version_property, kind_property)
        self._cache: dict[str, type[BaseModel]] = {}

    def to_pydantic(
        self, document: dict[str, Any], *, class_name: str = "Model"
    ) -> type[BaseModel]:
        """Materialize a Pydantic model from a schema document, cached by content."""
        key = json.dumps(document, sort_keys=True)
        if key not in self._cache:
            source = generate(
                json.dumps(document),
                input_file_type=InputFileType.JsonSchema,
                class_name=class_name,
            )
            namespace: dict[str, Any] = {}
            exec(str(source), namespace)
            self._cache[key] = namespace[class_name]
        return self._cache[key]

    def _field_default(self, model_cls: type[BaseModel], name: str) -> str:
        """Return the field's default value, mirroring the Pydantic adapter."""
        field_info: FieldInfo | None = model_cls.model_fields.get(name)
        if field_info is None:
            return ""
        default = field_info.default
        if default is PydanticUndefined or default is None:
            return ""
        return default if isinstance(default, str) else str(default)

    def version(self, model_cls: type[BaseModel]) -> str:
        return self._field_default(model_cls, self._version_property)

    def kind(self, model_cls: type[BaseModel]) -> str:
        return self._field_default(model_cls, self._kind_property)

    def finalize(
        self, target_model: type[BaseModel], data: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply model defaults and validate/serialize via the Pydantic model."""
        return target_model.model_validate(data).model_dump(by_alias=True)

    def validate(
        self,
        data: dict[str, Any],
        container: type[BaseModel],
        *,
        strict: bool = False,
    ) -> dict[str, Any]:
        """Validate *data* against the schema's Pydantic model."""
        if strict:
            return container.model_validate(data, strict=True).model_dump(by_alias=True)
        return container.model_validate(data).model_dump(by_alias=True)

    def resolve_model(self, annotation: Any) -> type[BaseModel] | None:
        """Return the first concrete ``BaseModel`` subclass inside *annotation*."""
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
        """Return the model class for *field_name* on the Pydantic model, if any."""
        field_info = parent_model.model_fields.get(field_name)
        if field_info is None:
            return None
        return self.resolve_model(field_info.annotation)

    def versionable(
        self, model_cls: type[VModel] | dict[str, Any]
    ) -> Versionable[VersionValue, VModel]:
        """Build a ``VersionNode`` wrapping the schema's Pydantic model.

        A JSON schema document is materialized into a Pydantic model first;
        an already-materialized model is used as-is.
        """
        if isinstance(model_cls, dict):
            model_cls = cast(type[VModel], self.to_pydantic(model_cls))
        return VersionNode[VersionValue, VModel](
            _model=model_cls,
            _value=self.of(self.version(model_cls)),
            _kind=self.kind(model_cls),
        )

    def diff(
        self,
        source: Versionable[VersionValue, VSource_co],
        target: Versionable[VersionValue, VTarget_co],
        *,
        is_backward_compatible: bool = False,
    ) -> Diff[VersionValue, VSource_co, VTarget_co]:
        """Compute a diff between two schema versions via their Pydantic models.

        A meta endpoint (``model is None``) yields a plain ``Diff`` with empty
        predicates — there is no schema to compare.
        """
        if source.model is None or target.model is None:
            return Diff(
                source=source,
                target=target,
                is_backward_compatible=is_backward_compatible,
            )
        return _pydantic_diff_pair(
            source,
            target,
            is_backward_compatible=is_backward_compatible,
        )


def _pydantic_diff_pair(
    source: Versionable[VersionValue, VSource_co],
    target: Versionable[VersionValue, VTarget_co],
    *,
    is_backward_compatible: bool = False,
) -> Diff[VersionValue, VSource_co, VTarget_co]:
    """Compute a :class:`Diff` by comparing two Pydantic models' fields."""
    if source.strategy != target.strategy:
        raise ValueError(
            f"Cannot create diff across strategies: "
            f"{source.strategy.__name__} != {target.strategy.__name__}"
        )
    if source.kind != target.kind:
        raise ValueError(
            f"Cannot create diff across kinds: {source.kind} != {target.kind}"
        )

    source_fields = source.model.model_fields
    target_fields = target.model.model_fields

    source_keys = set(source_fields.keys())
    target_keys = set(target_fields.keys())

    added = sorted(target_keys - source_keys)
    removed = sorted(source_keys - target_keys)
    common = source_keys & target_keys

    modified: dict[str, dict[str, Any]] = {}
    unchanged: list[str] = []
    for name in sorted(common):
        sf = source_fields[name]
        tf = target_fields[name]
        changes: dict[str, Any] = {}
        if sf.annotation != tf.annotation:
            changes["type_changed"] = {"from": sf.annotation, "to": tf.annotation}
        if sf.is_required() != tf.is_required():
            changes["required_changed"] = {
                "from": sf.is_required(),
                "to": tf.is_required(),
            }
        if changes:
            modified[name] = changes
        else:
            unchanged.append(name)

    added_info = {
        name: {
            "type": target_fields[name].annotation,
            "required": target_fields[name].is_required(),
            "default": target_fields[name].default,
        }
        for name in added
    }

    return Diff(
        source=source,
        target=target,
        added_fields=added,
        removed_fields=removed,
        modified_fields=modified,
        added_field_info=added_info,
        unchanged_fields=unchanged,
        is_backward_compatible=is_backward_compatible,
    )
