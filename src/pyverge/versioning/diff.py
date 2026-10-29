from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, Self, TypeVar

from pyverge.core.types import VersionValue

from .frozen import FrozenMap
from .schema import ModelDescriptor, NoDefault
from .types import (
    Comparable,
    Diffable,
    DiffMaterializer,
    DiffOrigin,
    DiffProvider,
    DiffRenderer,
    MigrationKey,
    Versionable,
)


class FieldStatus(StrEnum):
    """Delta status of one model field."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"

    def inverted(self) -> FieldStatus:
        return {
            FieldStatus.ADDED: FieldStatus.REMOVED,
            FieldStatus.REMOVED: FieldStatus.ADDED,
        }.get(self, self)


@dataclass(frozen=True, slots=True)
class FieldChange:
    """One field's delta status and details."""

    status: FieldStatus
    details: Mapping[str, Any]


@dataclass(frozen=True)
class Diff(Generic[VersionValue]):
    """Differences between two model versions — data with queryable predicates.

    Provider-specific construction computes the field changes. ``origin``
    records how the diff was produced.
    """

    source: Versionable[VersionValue]
    target: Comparable[VersionValue]
    fields: FrozenMap[str, FieldChange]
    origin: DiffOrigin

    @classmethod
    def from_pair(
        cls,
        source: Versionable[VersionValue],
        target: Comparable[VersionValue],
        *,
        adapter: DiffProvider,
    ) -> Self:
        diff = adapter.diff(source, target)
        return cls(
            source=diff.source,
            target=diff.target,
            fields=diff.fields,
            origin=diff.origin,
        )

    def with_field(self, name: str, change: FieldChange) -> Self:
        return type(self)(
            source=self.source,
            target=self.target,
            fields=self.fields.updated({name: change}),
            origin=self.origin,
        )

    def with_fields(self, changes: Mapping[str, FieldChange]) -> Self:
        return type(self)(
            source=self.source,
            target=self.target,
            fields=self.fields.updated(changes),
            origin=self.origin,
        )

    def render(self, renderer: DiffRenderer[Any]) -> Any:
        return renderer.render(self)

    def materialize(self, materializer: DiffMaterializer[Any]) -> Any:
        return materializer.materialize(self)

    def fingerprint_payload(self) -> Mapping[str, Any]:
        return {
            "fields": {
                name: {
                    "status": change.status.value,
                    "details": change.details,
                }
                for name, change in sorted(self.fields.items())
            },
            "origin": self.origin,
        }

    @property
    def field_changes(self) -> ChangeSet[str]:
        return ChangeSet(
            added=frozenset(self.added_fields),
            removed=frozenset(self.removed_fields),
            modified=frozenset(self.modified_fields),
        )

    @property
    def added_fields(self) -> list[str]:
        return sorted(
            name
            for name, change in self.fields.items()
            if change.status is FieldStatus.ADDED
        )

    @property
    def removed_fields(self) -> list[str]:
        return sorted(
            name
            for name, change in self.fields.items()
            if change.status is FieldStatus.REMOVED
        )

    @property
    def modified_fields(self) -> dict[str, dict[str, Any]]:
        return {
            name: dict(change.details)
            for name, change in sorted(self.fields.items())
            if change.status is FieldStatus.MODIFIED
        }

    @property
    def added_field_info(self) -> dict[str, dict[str, Any]]:
        return {
            name: dict(change.details)
            for name, change in sorted(self.fields.items())
            if change.status is FieldStatus.ADDED
        }

    @property
    def unchanged_fields(self) -> list[str]:
        return sorted(
            name
            for name, change in self.fields.items()
            if change.status is FieldStatus.UNCHANGED
        )

    @property
    def kind(self) -> str:
        return self.source.kind

    @property
    def edge(self) -> MigrationKey:
        return (self.source.id, self.target.id)

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
        change = self.fields.get(field)
        return change is not None and change.status is FieldStatus.ADDED

    def is_removed(self, field: str) -> bool:
        change = self.fields.get(field)
        return change is not None and change.status is FieldStatus.REMOVED

    def is_modified(self, field: str) -> bool:
        change = self.fields.get(field)
        return change is not None and change.status is FieldStatus.MODIFIED

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

    def inverted(self) -> Diff[VersionValue]:
        swapped = {
            name: FieldChange(
                status=change.status.inverted(),
                details=change.details,
            )
            for name, change in self.fields.items()
        }
        return Diff(
            source=self.source,
            target=self.target,
            fields=FrozenMap(swapped),
            origin=self.origin,
        )


T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class ChangeSet(Generic[T]):
    """Added, removed, and modified identities in one delta."""

    added: frozenset[T] = frozenset()
    removed: frozenset[T] = frozenset()
    modified: frozenset[T] = frozenset()

    @property
    def changed(self) -> bool:
        return bool(self.added or self.removed or self.modified)

    def summary(self, label: str) -> list[str]:
        lines: list[str] = []
        for verb, values in (
            ("added", self.added),
            ("removed", self.removed),
            ("changed", self.modified),
        ):
            if values:
                rendered = ", ".join(str(value) for value in sorted(values, key=str))
                lines.append(f"{label} {verb}: {rendered}")
        return lines


def _build_diff(
    source: Versionable[VersionValue],
    target: Comparable[VersionValue],
) -> Diff[VersionValue]:
    source_descriptor = getattr(source, "descriptor", None)
    target_descriptor = getattr(target, "descriptor", None)
    fields: FrozenMap[str, FieldChange] = FrozenMap()
    if source_descriptor is not None and target_descriptor is not None:
        if source.strategy != target.strategy:
            raise ValueError(
                f"Cannot create diff across strategies: "
                f"{source.strategy.__name__} != {target.strategy.__name__}"
            )
        if source.kind != target.kind:
            raise ValueError(
                f"Cannot create diff across kinds: {source.kind} != {target.kind}"
            )
        fields = _diff_fields(source_descriptor, target_descriptor)
    return Diff(
        source=source,
        target=target,
        fields=fields,
        origin=DiffOrigin.SCHEMA,
    )


def _diff_fields(
    source: ModelDescriptor,
    target: ModelDescriptor,
) -> FrozenMap[str, FieldChange]:
    source_fields = source.fields
    target_fields = target.fields
    source_keys = set(source_fields)
    target_keys = set(target_fields)

    fields: dict[str, FieldChange] = {}
    for name in sorted(target_keys - source_keys):
        field = target_fields[name]
        fields[name] = FieldChange(
            FieldStatus.ADDED,
            {
                "type": field.annotation,
                "type_ref": field.type_ref.to_canonical(),
                "required": field.required,
                "default": None
                if isinstance(field.default, NoDefault)
                else field.default,
            },
        )
    for name in sorted(source_keys - target_keys):
        fields[name] = FieldChange(FieldStatus.REMOVED, {})
    for name in sorted(source_keys & target_keys):
        source_field = source_fields[name]
        target_field = target_fields[name]
        changes: dict[str, Any] = {}
        if source_field.type_ref != target_field.type_ref:
            changes["type_changed"] = {
                "from": source_field.type_ref.to_canonical(),
                "to": target_field.type_ref.to_canonical(),
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
    return FrozenMap(fields)


__all__ = [
    "BackwardCompatibilityGuard",
    "ChangeSet",
    "CompatibilityReport",
    "Diff",
    "DiffOrigin",
    "FieldChange",
    "FieldStatus",
]


@dataclass(frozen=True, slots=True)
class CompatibilityReport:
    """Structural compatibility of one version transition.

    Identity fields are excluded by the caller: they change on every version
    and must not be reported as breaking schema changes.
    """

    kind: str
    source_version: str
    target_version: str
    added_fields: tuple[str, ...]
    removed_fields: tuple[str, ...]
    modified_fields: tuple[str, ...]
    structural_breaking: bool

    @classmethod
    def from_diff(
        cls,
        diff: Diffable,
        *,
        identity_fields: frozenset[str],
    ) -> Self:
        added = tuple(
            field for field in diff.added_fields if field not in identity_fields
        )
        removed = tuple(
            field for field in diff.removed_fields if field not in identity_fields
        )
        modified = {
            field: change
            for field, change in diff.modified_fields.items()
            if field not in identity_fields
        }
        structural = (
            bool(removed)
            or any("type_changed" in change for change in modified.values())
            or any("required_changed" in change for change in modified.values())
            or any(diff.is_added_required(field) for field in added)
        )
        return cls(
            kind=diff.source.kind,
            source_version=str(diff.source.version),
            target_version=str(diff.target.version),
            added_fields=added,
            removed_fields=removed,
            modified_fields=tuple(sorted(modified)),
            structural_breaking=structural,
        )


@dataclass(frozen=True, slots=True)
class BackwardCompatibilityGuard:
    """Evaluate whether a declared compatible transition is structural breaking."""

    identity_fields: frozenset[str]

    def evaluate(self, diff: Diffable) -> CompatibilityReport:
        return CompatibilityReport.from_diff(
            diff,
            identity_fields=self.identity_fields,
        )

    def required_additions(
        self,
        diff: Diffable,
        report: CompatibilityReport,
    ) -> tuple[str, ...]:
        return tuple(
            field for field in report.added_fields if diff.is_added_required(field)
        )
