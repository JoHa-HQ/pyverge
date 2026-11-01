from __future__ import annotations

from pyverge.versioning import Identifiable, VersionKey

from ..types import GraphCatalog, HealthIssue


class MissingReferencesLinter:
    """Report descriptor references absent from the local namespace."""

    def __call__(
        self,
        catalog: GraphCatalog,
        entity: Identifiable,
    ) -> tuple[HealthIssue, ...]:
        """Return missing-reference issues for a node.

        Args:
            catalog: Registry surface used for local lookups.
            entity: Candidate node identity.

        Returns:
            tuple[HealthIssue, ...]: Missing-reference issues.
        """
        if not isinstance(entity, VersionKey):
            return ()
        issues: list[HealthIssue] = []
        for reference in getattr(entity, "references", frozenset()):
            local = reference.namespace == catalog.namespace
            if local and catalog.has_model(reference):
                continue
            code = (
                "reference.missing.local" if local else "reference.missing.namespaced"
            )
            issues.append(
                HealthIssue(
                    code=code,
                    severity="error",
                    entity=entity,
                    message=f"{entity} references missing version {reference}",
                    details={"reference": reference},
                )
            )
        return tuple(issues)


__all__ = ["MissingReferencesLinter"]
