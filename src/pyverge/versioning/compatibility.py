from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from .types import Diffable


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
