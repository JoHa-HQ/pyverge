from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Self

from pydantic import BaseModel, create_model
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

logger = logging.getLogger(__name__)


class PydanticModelAdapter(AbstractModelAdapter):
    def _field_default(self, model_cls: ModelHandle, name: str) -> str:
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
        """Report whether *container* is a Pydantic model.

        With *fields*, require at least one model reachable from the container
        (the container itself, or a nested/union member) to declare every one
        of them — so a wrapper container hosting a versioned union still covers
        the migrated shape.
        """
        if not (isinstance(container, type) and issubclass(container, BaseModel)):
            return False
        if fields is None:
            return True
        for model in self._reachable_models(container):
            if fields <= set(model.model_fields):
                return True
        return False

    def _reachable_models(self, container: type[BaseModel]) -> list[type[BaseModel]]:
        """Return *container* plus every model reachable from its fields."""
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
        """Build a typed Pydantic instance from a migrated payload."""
        return container.model_validate(data)

    def finalize(
        self, target_model: ModelHandle, data: dict[str, Any]
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
        container: ModelHandle,
        *,
        strict: bool = False,
    ) -> dict[str, Any]:
        """Validate *data* against *container* and return the dumped payload."""
        if strict:
            return container.model_validate(data, strict=True).model_dump(by_alias=True)
        return container.model_validate(data).model_dump(by_alias=True)

    def resolve_model(self, annotation: Any) -> ModelHandle | None:
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
        self, parent_model: ModelHandle, field_name: str
    ) -> ModelHandle | None:
        """Return the model class for *field_name* on *parent_model*, if any."""
        field_info = parent_model.model_fields.get(field_name)
        if field_info is None:
            return None
        return self.resolve_model(field_info.annotation)

    def references(self, model_cls: ModelHandle) -> frozenset[ModelVersionKey]:
        """Return every versioned ``(kind, version)`` the model's fields declare.

        Walks the field annotations recursively and collects **all** model
        classes they mention — every member of a ``Union``, ``list`` items,
        through ``Annotated`` wrappers — unlike ``resolve_model``, which
        collapses a union to its first member.  A model that declares three
        versions of a nested kind therefore reports all three.

        Only versioned nested models contribute (an unversioned ``BaseModel``
        has an empty ``kind`` and is skipped).  Cycles are tolerated.
        """
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
        """Return every ``BaseModel`` class mentioned in *annotation*.

        Unwraps ``Annotated``, ``Union``/``Optional`` and ``list``/``tuple``
        containers, collecting all members rather than the first.
        """
        if isinstance(annotation, type) and issubclass(annotation, BaseModel):
            return [annotation]

        models: list[ModelHandle] = []
        for arg in getattr(annotation, "__args__", ()):
            models.extend(self._iter_models(arg))
        return models

    def versionable(
        self,
        model_cls: ModelHandle | None,
        *,
        kind: str | None = None,
        version: str | None = None,
    ) -> Versionable[VersionValue]:
        """Build a ``VersionNode`` wrapping *model_cls* using its encoded metadata.

        With ``None`` as the model, a meta node (no concrete model) is built
        from *kind* and *version* strings.
        """
        if model_cls is not None:
            return VersionNode[VersionValue](
                _model=model_cls,
                _value=self.of(self.version(model_cls)),
                _kind=self.kind(model_cls),
                references=self.references(model_cls),
                fields=self.fields(model_cls),
            )
        if kind is None or version is None:
            raise ValueError("kind and version are required for a meta versionable")
        return VersionNode[VersionValue](
            _model=None,
            _value=self.of(version),
            _kind=kind,
        )

    def diff(
        self,
        source: Versionable[VersionValue],
        target: Versionable[VersionValue],
        *,
        is_backward_compatible: bool = False,
    ) -> Diff[VersionValue]:
        """Compute a diff between two model versions.

        A meta endpoint (``model is None``) yields a plain ``Diff`` with empty
        predicates — there is no schema to compare.
        """
        if source.model is None or target.model is None:
            return Diff(
                source=source,
                target=target,
                is_backward_compatible=is_backward_compatible,
            )
        return PydanticDiff.from_pair(
            source,
            target,
            is_backward_compatible=is_backward_compatible,
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

    def materialize_model(
        self,
        diff: Diffable[VersionValue],
    ) -> ModelHandle:
        """Materialize a model from a diff's anchor and target version.

        The anchor's fields are copied, fields removed by the diff are dropped,
        and fields added by the diff are appended with their recorded type and
        default.  The ``version`` field is pinned to the reconstructed version.
        """
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


@dataclass(frozen=True)
class PydanticDiff(Diff[VersionValue]):
    """Differences between two Pydantic model versions.

    Computed eagerly from two Pydantic model classes.  No migration logic —
    callers query the diff to decide what to do.  Render output via the
    pluggable ``renderer`` strategy.
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
        *,
        is_backward_compatible: bool = False,
    ) -> Self:
        """Compute a :class:`PydanticDiff` by comparing two Pydantic models."""
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

        for fn in sorted(common):
            sf = source_fields[fn]
            tf = target_fields[fn]
            changes = cls._diff_fields(sf, tf)
            if changes:
                modified[fn] = changes
            else:
                unchanged.append(fn)

        added_info = {}
        for fn in added:
            tf = target_fields[fn]
            added_info[fn] = {
                "type": tf.annotation,
                "required": tf.is_required(),
                "default": tf.default if tf.default is not PydanticUndefined else None,
            }

        return cls(
            source=source,
            target=target,
            added_fields=added,
            removed_fields=removed,
            modified_fields=modified,
            added_field_info=added_info,
            unchanged_fields=unchanged,
            is_backward_compatible=is_backward_compatible,
        )
