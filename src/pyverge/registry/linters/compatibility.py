from __future__ import annotations

from dataclasses import dataclass

from pyverge.versioning import (
    BackwardCompatibilityGuard,
    EdgeKey,
    Identifiable,
    VersionEdge,
)

from ..types import GraphCatalog, HealthIssue


@dataclass(frozen=True, slots=True)
class CompatibilityLinter:
    """Report structurally breaking migrations."""

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
        guard = BackwardCompatibilityGuard(self.identity_fields)
        report = guard.evaluate(entity.diff)
        if not report.structural_breaking:
            return ()
        required = guard.required_additions(entity.diff, report)
        return (
            HealthIssue(
                code="migration.structural_breaking",
                severity="error",
                entity=EdgeKey.from_version_edge(entity),
                message=(f"{entity.source} → {entity.target} is structurally breaking"),
                details={
                    "removed": report.removed_fields,
                    "modified": report.modified_fields,
                    "required_additions": required,
                },
            ),
        )


__all__ = ["CompatibilityLinter"]
