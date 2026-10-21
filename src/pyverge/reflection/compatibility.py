"""Backward-compatibility analysis for a schema diff."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from pyverge.core.types import Diffable


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
    declared_backward_compatible: bool

    @classmethod
    def from_diff(
        cls,
        diff: Diffable,
        *,
        identity_fields: frozenset[str],
    ) -> Self:
        """Build a report from a diff, excluding identity fields."""
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
            declared_backward_compatible=diff.is_backward_compatible,
        )

    @property
    def breaking(self) -> bool:
        """Whether the transition is breaking under its declared policy."""
        return self.structural_breaking and not self.declared_backward_compatible
