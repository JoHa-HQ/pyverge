from __future__ import annotations

from dataclasses import dataclass

from pyverge.core.versioning import Diffable, EdgeKey, Identifiable, VersionEdge

from ..types import GraphCatalog, HealthIssue


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
    ) -> CompatibilityReport:
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

    def required_additions(self, diff: Diffable) -> tuple[str, ...]:
        """Return added fields that are required in the target."""
        return tuple(
            field for field in self.added_fields if diff.is_added_required(field)
        )


@dataclass(frozen=True, slots=True)
class CompatibilityLinter:
    """Report structurally breaking migrations.

    Structural breaks are reported as ``warning``: they are a deliberate
    migration choice, so they appear in the health index without blocking a
    startup validation policy that raises on ``error``.
    """

    identity_fields: frozenset[str]

    def __call__(
        self,
        catalog: GraphCatalog,
        entity: Identifiable,
    ) -> tuple[HealthIssue, ...]:
        """Return compatibility issues for one executable edge.

        Args:
            catalog: Registry surface used for edge discovery.
            entity: Candidate graph entity.

        Returns:
            tuple[HealthIssue, ...]: Compatibility issues for the edge.
        """
        if not isinstance(entity, VersionEdge):
            return ()
        report = CompatibilityReport.from_diff(
            entity.diff,
            identity_fields=self.identity_fields,
        )
        if not report.structural_breaking:
            return ()
        required = report.required_additions(entity.diff)
        return (
            HealthIssue(
                code="migration.structural_breaking",
                severity="warning",
                entity=EdgeKey.from_version_edge(entity),
                message=(f"{entity.source} → {entity.target} is structurally breaking"),
                details={
                    "removed": report.removed_fields,
                    "modified": report.modified_fields,
                    "required_additions": required,
                },
            ),
        )


__all__ = [
    "CompatibilityLinter",
    "CompatibilityReport",
]
