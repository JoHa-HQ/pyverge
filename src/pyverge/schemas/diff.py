"""Provider-neutral field diff construction."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pyverge.core.types import ModelHandle, VersionValue
from pyverge.versioning import (
    Comparable,
    Diff,
    DiffOrigin,
    FieldChange,
    FieldStatus,
    Versionable,
)


@dataclass(frozen=True, slots=True)
class FieldDescriptor:
    """Provider-neutral description of one model field."""

    name: str
    annotation: Any
    required: bool
    default: Any


class SchemaDiffer:
    """Build a schema diff from adapter-provided field descriptors."""

    def diff(
        self,
        source: Versionable[VersionValue],
        target: Comparable[VersionValue],
        describe: Callable[[ModelHandle], Mapping[str, FieldDescriptor]],
    ) -> Diff[VersionValue]:
        """Build a diff; a meta target yields an empty field set."""
        target_model = getattr(target, "model", None)
        fields = {}
        if target_model is not None:
            fields = self.fields(source.model, target_model, describe)
        return Diff(
            source=source,
            target=target,
            fields=fields,
            origin=DiffOrigin.SCHEMA,
        )

    def fields(
        self,
        source_model: ModelHandle,
        target_model: ModelHandle,
        describe: Callable[[ModelHandle], Mapping[str, FieldDescriptor]],
    ) -> Mapping[str, FieldChange]:
        """Compare two field descriptor mappings."""
        source_fields = describe(source_model)
        target_fields = describe(target_model)
        source_keys = set(source_fields)
        target_keys = set(target_fields)

        fields: dict[str, FieldChange] = {}
        for name in sorted(target_keys - source_keys):
            field = target_fields[name]
            fields[name] = FieldChange(
                FieldStatus.ADDED,
                {
                    "type": field.annotation,
                    "required": field.required,
                    "default": field.default,
                },
            )
        for name in sorted(source_keys - target_keys):
            fields[name] = FieldChange(FieldStatus.REMOVED, {})
        for name in sorted(source_keys & target_keys):
            source_field = source_fields[name]
            target_field = target_fields[name]
            changes: dict[str, Any] = {}
            if source_field.annotation != target_field.annotation:
                changes["type_changed"] = {
                    "from": source_field.annotation,
                    "to": target_field.annotation,
                }
            if source_field.required != target_field.required:
                changes["required_changed"] = {
                    "from": source_field.required,
                    "to": target_field.required,
                }
            if source_field.default != target_field.default:
                changes["default_changed"] = {
                    "from": source_field.default,
                    "to": target_field.default,
                }
            fields[name] = FieldChange(
                FieldStatus.MODIFIED if changes else FieldStatus.UNCHANGED,
                changes,
            )
        return fields


__all__ = ["FieldDescriptor", "SchemaDiffer"]
