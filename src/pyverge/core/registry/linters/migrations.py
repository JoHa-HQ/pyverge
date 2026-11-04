from __future__ import annotations

from itertools import pairwise

from pyverge.core.versioning import EdgeKey, Identifiable, VersionKey

from ..types import GraphCatalog, HealthIssue


class MissingMigrationsLinter:
    """Report adjacent model versions without an executable migration."""

    def __call__(
        self,
        catalog: GraphCatalog,
        entity: Identifiable,
    ) -> tuple[HealthIssue, ...]:
        """Return missing-migration issues for one model version.

        Args:
            catalog: Registry surface used for version and migration lookups.
            entity: Candidate model version.

        Returns:
            tuple[HealthIssue, ...]: Missing-migration issues for the next
                adjacent version.
        """
        if not isinstance(entity, VersionKey):
            return ()
        versions = catalog.kind_versions(entity.kind)
        for source, target in pairwise(versions):
            if source != entity or source.namespace != target.namespace:
                continue
            edge = EdgeKey.from_pair(source, target)
            if catalog.has_migration(edge):
                return ()
            return (
                HealthIssue(
                    code="migration.missing",
                    severity="error",
                    entity=edge,
                    message=(
                        f"{source.kind}: missing migration "
                        f"{source.version} -> {target.version}"
                    ),
                    details={"source": source, "target": target},
                ),
            )
        return ()


__all__ = ["MissingMigrationsLinter"]
