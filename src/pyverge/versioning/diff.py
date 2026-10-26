from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Generic, Self

from pyverge.core.types import VersionValue

from .graph import ChangeSet
from .types import (
    Comparable,
    Diffable,
    DiffMaterializer,
    DiffOrigin,
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

    Provider-specific construction (e.g. ``PydanticDiff.from_pair``) computes
    the field changes. ``origin`` records how the diff was produced.
    """

    source: Versionable[VersionValue]
    target: Comparable[VersionValue]
    fields: Mapping[str, FieldChange]
    origin: DiffOrigin

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
            fields=swapped,
            origin=self.origin,
        )


__all__ = [
    "BackwardCompatibilityGuard",
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
            source_version=str(diff.source.version[1]),
            target_version=str(diff.target.version[1]),
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
