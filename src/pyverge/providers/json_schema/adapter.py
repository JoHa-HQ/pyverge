from __future__ import annotations

import json
from typing import Any

from datamodel_code_generator import InputFileType, generate
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from pyverge.core.render import JsonPatchRender
from pyverge.core.types import (
    Diffable,
    ModelData,
    ModelHandle,
    ModelVersionKey,
    Versionable,
    VersionValue,
)
from pyverge.core.versioning import (
    VersionNode,
)
from pyverge.providers.base import AbstractModelAdapter
from pyverge.providers.json_patch.migration import JsonPatchMigration
from pyverge.reflection.diff import Diff


class JsonSchemaModelAdapter(AbstractModelAdapter):
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
        self._cache: dict[str, ModelHandle] = {}

    def to_pydantic(
        self, document: dict[str, Any], *, class_name: str = "Model"
    ) -> ModelHandle:
        """Materialize a Pydantic model from a schema document, cached by content.

        The generated module may define multiple classes for nested/referenced
        schemas (via ``$defs``/``definitions``); each is rebuilt against the
        module namespace so forward references resolve to concrete classes
        rather than staying ``ForwardRef``.

        Returns:
            The materialized model class for *class_name*.
        """
        key = json.dumps(document, sort_keys=True)
        if key not in self._cache:
            source = generate(
                json.dumps(document),
                input_file_type=InputFileType.JsonSchema,
                class_name=class_name,
            )
            namespace: dict[str, Any] = {}
            exec(str(source), namespace)
            self._rebuild(namespace)
            self._cache[key] = namespace[class_name]
        return self._cache[key]

    @staticmethod
    def _rebuild(namespace: dict[str, Any]) -> None:
        """Resolve forward references for every model in the generated module."""
        for obj in list(namespace.values()):
            if isinstance(obj, type) and issubclass(obj, BaseModel):
                try:
                    obj.model_rebuild(_types_namespace=namespace)
                except Exception:  # best-effort; generic models skip rebuild
                    continue

    def _field_default(self, model_cls: ModelHandle, name: str) -> str:
        """Return the field's default value, mirroring the Pydantic adapter."""
        field_info: FieldInfo | None = model_cls.model_fields.get(name)
        if field_info is None:
            return ""
        default = field_info.default
        if default is PydanticUndefined or default is None:
            return ""
        return default if isinstance(default, str) else str(default)

    def version(self, model_cls: ModelHandle) -> str:
        return self._field_default(model_cls, self._version_property)

    def kind(self, model_cls: ModelHandle) -> str:
        return self._field_default(model_cls, self._kind_property)

    def identify(self, model_cls: ModelHandle) -> bool:
        """Return whether *model_cls* is a Pydantic model this adapter owns."""
        return isinstance(model_cls, type) and issubclass(model_cls, BaseModel)

    def can_handle(
        self,
        container: Any,
        *,
        fields: frozenset[str] | None = None,
    ) -> bool:
        """Report whether *container* is a materialized schema model.

        With *fields*, also require the model to declare every one of them.
        """
        if not (isinstance(container, type) and issubclass(container, BaseModel)):
            return False
        if fields is None:
            return True
        return fields <= set(container.model_fields)

    def instantiate(self, container: ModelHandle, data: ModelData) -> Any:
        """Build a typed Pydantic instance from a migrated payload."""
        return container.model_validate(data)

    def finalize(
        self, target_model: ModelHandle, data: dict[str, Any]
    ) -> dict[str, Any]:
        """Apply model defaults and validate/serialize via the Pydantic model."""
        return target_model.model_validate(data).model_dump(by_alias=True)

    def validate(
        self,
        data: dict[str, Any],
        container: ModelHandle,
        *,
        strict: bool = False,
    ) -> dict[str, Any]:
        """Validate *data* against the schema's Pydantic model."""
        if strict:
            return container.model_validate(data, strict=True).model_dump(by_alias=True)
        return container.model_validate(data).model_dump(by_alias=True)

    def resolve_model(self, annotation: Any) -> ModelHandle | None:
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
        self, parent_model: ModelHandle, field_name: str
    ) -> ModelHandle | None:
        """Return the model class for *field_name* on the Pydantic model, if any."""
        field_info = parent_model.model_fields.get(field_name)
        if field_info is None:
            return None
        return self.resolve_model(field_info.annotation)

    def references(self, model_cls: ModelHandle) -> frozenset[ModelVersionKey]:
        """Return every versioned ``(kind, version)`` the model's fields declare."""
        found: set[ModelVersionKey] = set()
        self._collect_references(model_cls, found, set())
        return frozenset(found)

    def _collect_references(
        self,
        model_cls: ModelHandle,
        found: set[Any],
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

    def versionable(
        self,
        model_cls: ModelHandle | dict[str, Any] | None,
        *,
        kind: str | None = None,
        version: str | None = None,
    ) -> Versionable[VersionValue]:
        """Build a ``VersionNode`` wrapping the schema's Pydantic model.

        A JSON schema document is materialized into a Pydantic model first;
        an already-materialized model is used as-is.  With ``None`` as the
        model, a meta node (no concrete model) is built from *kind* and
        *version* strings.
        """
        if model_cls is None:
            if kind is None or version is None:
                raise ValueError("kind and version are required for a meta versionable")
            return VersionNode[VersionValue](
                _model=None,
                _value=self.of(version),
                _kind=kind,
            )
        model: ModelHandle
        if isinstance(model_cls, dict):
            model = self.to_pydantic(model_cls)
        else:
            model = model_cls
        return VersionNode[VersionValue](
            _model=model,
            _value=self.of(self.version(model)),
            _kind=self.kind(model),
            references=self.references(model),
            fields=self.fields(model),
        )

    def diff(
        self,
        source: Versionable[VersionValue],
        target: Versionable[VersionValue],
        *,
        is_backward_compatible: bool = False,
    ) -> Diff[VersionValue]:
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

    def materialize_model(
        self,
        diff: Diffable[VersionValue],
    ) -> ModelHandle:
        """Materialize a schema model from a diff's anchor and target version.

        The anchor's JSON Schema document is rebuilt: removed fields are
        dropped from ``properties``/``required``, added fields are appended
        with their recorded type/default, and the ``version`` default is
        pinned to the reconstructed version.  The document is then
        re-materialized into a Pydantic model.
        """
        anchor = diff.source.model
        version = diff.target.version[1]
        document = anchor.model_json_schema()
        properties = document.setdefault("properties", {})
        required = document.get("required", [])

        for name in diff.removed_fields:
            properties.pop(name, None)
            if name in required:
                required.remove(name)

        for name in diff.added_fields:
            if name in properties:
                continue
            info = diff.added_field_info.get(name, {})
            prop: dict[str, Any] = {}
            annotation = info.get("type")
            if annotation is not None:
                prop["type"] = _json_type(annotation)
            default = info.get("default")
            if default is not None:
                prop["default"] = default
            if info.get("required"):
                if name not in required:
                    required.append(name)
            properties[name] = prop

        if self._version_property in properties:
            properties[self._version_property]["default"] = str(version)

        return self.to_pydantic(
            document, class_name=f"ModelV{str(version).replace('.', '')}"
        )

    def materialize_migration(
        self,
        diff: Diffable[VersionValue],
    ) -> JsonPatchMigration:
        """Materialize an RFC 6902 JSON Patch migration from a diff."""
        spec = {
            "from": str(diff.source.version[1]),
            "to": str(diff.target.version[1]),
            "ops": JsonPatchRender(diff)(),
        }
        return JsonPatchMigration(spec)


def _json_type(annotation: Any) -> str:
    """Map a Python annotation to a JSON Schema type name."""
    if annotation is bool:
        return "boolean"
    if annotation is int:
        return "integer"
    if annotation is float:
        return "number"
    if annotation is str:
        return "string"
    origin = getattr(annotation, "__origin__", None)
    if origin is list:
        return "array"
    if origin is dict:
        return "object"
    return "string"


def _pydantic_diff_pair(
    source: Versionable[VersionValue],
    target: Versionable[VersionValue],
    *,
    is_backward_compatible: bool = False,
) -> Diff[VersionValue]:
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
