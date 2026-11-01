from __future__ import annotations

from pyverge.versioning import EdgeKey, Identifiable

from ..types import GraphCatalog, HealthIssue


class MissingEdgeEndpointsLinter:
    """Report edge endpoints absent from the local registry."""

    def __call__(
        self,
        catalog: GraphCatalog,
        entity: Identifiable,
    ) -> tuple[HealthIssue, ...]:
        """Return endpoint issues for an edge.

        Args:
            catalog: Registry surface used for endpoint lookups.
            entity: Candidate edge identity.

        Returns:
            Endpoint and namespace issues.
        """
        if not isinstance(entity, EdgeKey):
            return ()
        issues: list[HealthIssue] = []
        for endpoint in entity.key:
            if endpoint.namespace != catalog.namespace:
                issues.append(
                    HealthIssue(
                        code="namespace.unresolved",
                        severity="error",
                        entity=entity,
                        message=(
                            f"{entity} endpoint {endpoint} is outside "
                            f"{catalog.namespace!r}"
                        ),
                        details={"endpoint": endpoint},
                    )
                )
            elif not catalog.has_entry(endpoint):
                issues.append(
                    HealthIssue(
                        code="edge.endpoint.missing",
                        severity="error",
                        entity=entity,
                        message=f"{entity} endpoint {endpoint} is not registered",
                        details={"endpoint": endpoint},
                    )
                )
        return tuple(issues)


__all__ = ["MissingEdgeEndpointsLinter"]
