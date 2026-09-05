"""Provider-specific model adapters.

A :class:`ModelAdapter` is the only place allowed to know how a model
class encodes its ``version`` and ``kind``.  The rest of the migration
machinery works with :class:`Versionable` objects and never touches
provider-specific introspection APIs directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Generic, Self, cast

import pendulum
from pydantic import BaseModel
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined
from semver import Version

from ..render import JsonPatchRender
from ..types import (
    MigrationKey,
    Renderable,
    Versionable,
    VersionValue,
    VModel,
    VSource_co,
    VTarget_co,
)
from ..versioning import VersionNode

logger = logging.getLogger(__name__)


class PydanticModelAdapter:
    """Adapter for Pydantic ``BaseModel`` subclasses."""

    def __init__(
        self,
        version_property: str = "version",
        kind_property: str = "kind",
    ) -> None:
        self._version_property = version_property
        self._kind_property = kind_property

    @classmethod
    def of(cls, value: str) -> VersionValue:
        """Parse a version string (mostly coming from Literal), then determine the strategy"""  # noqa: E501
        try:
            return cast(VersionValue, Version.parse(value))
        except ValueError:
            logger.debug(f"Failed to parse semver: {value!r}")

        try:
            parsed = pendulum.parse(str(value), exact=True)
            if isinstance(parsed, pendulum.DateTime):
                parsed = parsed.date()
            if not isinstance(parsed, pendulum.Date):
                raise ValueError(f"Expected date, got {parsed!r}")
            return cast(VersionValue, parsed)
        except ValueError:
            logger.debug(f"Failed to parse date: {value!r}")

        msg = (
            f"Cannot parse version {value!r}. "
            "Expected semver (e.g. '1.0.0') or ISO date (e.g. '2024-06-01')."
        )
        raise ValueError(msg)

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
    ) -> PydanticDiff[VersionValue, VSource_co, VTarget_co]:
        """Compute a diff between two Pydantic model versions."""
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


@dataclass(frozen=True)
class PydanticDiff(Generic[VersionValue, VSource_co, VTarget_co]):
    """Differences between two model versions — data with queryable predicates.

    Computed eagerly from two Pydantic model classes.  No migration logic —
    callers query the diff to decide what to do.  Render output via the
    pluggable ``renderer`` strategy.
    """

    source: Versionable[VersionValue, VSource_co]
    target: Versionable[VersionValue, VTarget_co]
    added_fields: list[str] = field(default_factory=list)
    removed_fields: list[str] = field(default_factory=list)
    modified_fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    added_field_info: dict[str, dict[str, Any]] = field(default_factory=dict)
    unchanged_fields: list[str] = field(default_factory=list)
    renderer: type[JsonPatchRender] = field(default=JsonPatchRender)
    is_backward_compatible: bool = False

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

    @property
    def kind(self) -> str:
        return self.source.kind

    @property
    def edge(self) -> MigrationKey:
        return (self.source, self.target)

    @property
    def is_backward(self) -> bool:
        return self.source > self.target

    @property
    def is_forward(self) -> bool:
        return self.source < self.target

    @property
    def is_identity(self) -> bool:
        return (
            not self.added_fields
            and not self.removed_fields
            and not self.modified_fields
        )

    @property
    def has_additions(self) -> bool:
        return bool(self.added_fields)

    @property
    def has_removals(self) -> bool:
        return bool(self.removed_fields)

    @property
    def has_modifications(self) -> bool:
        return bool(self.modified_fields)

    @property
    def has_type_changes(self) -> bool:
        return any("type_changed" in c for c in self.modified_fields.values())

    @property
    def has_constraint_changes(self) -> bool:
        return any("required_changed" in c for c in self.modified_fields.values())

    def is_added(self, field: str) -> bool:
        return field in self.added_fields

    def is_removed(self, field: str) -> bool:
        return field in self.removed_fields

    def is_modified(self, field: str) -> bool:
        return field in self.modified_fields

    def is_added_required(self, field: str) -> bool:
        info = self.added_field_info.get(field)
        return bool(info and info.get("required"))

    def added_default(self, field: str) -> Any:
        info = self.added_field_info.get(field)
        return info.get("default") if info else None

    def modified_change(self, field: str, key: str) -> Any | None:
        return self.modified_fields.get(field, {}).get(key)

    def is_union_expansion(self, field: str) -> bool:
        rc = self.modified_change(field, "required_changed")
        return rc is not None and rc["from"] and not rc["to"]

    def is_union_contraction(self, field: str) -> bool:
        rc = self.modified_change(field, "required_changed")
        return rc is not None and not rc["from"] and rc["to"]

    @property
    def render(self) -> Renderable:
        """Render this diff using the configured strategy."""
        return self.renderer(self)

    @classmethod
    def from_pair(
        cls: type[Self],
        source: Versionable[VersionValue, VSource_co],
        target: Versionable[VersionValue, VTarget_co],
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
