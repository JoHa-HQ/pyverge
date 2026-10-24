"""Catalog health diagnostics for CI and doctor commands."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Literal

from pyverge.versioning import EdgeKey

from .catalog.ports import GraphCatalog


@dataclass(frozen=True, slots=True)
class HealthReport:
    """Catalog health snapshot."""

    kinds: int
    versions: int
    issues: tuple[str, ...] = ()

    @property
    def status(self) -> Literal["ok", "error"]:
        """Overall status."""
        return "ok" if not self.issues else "error"

    def to_dict(self, *, manager: str | None = None) -> dict[str, object]:
        """Serialize for CLI/JSON consumers."""
        report: dict[str, object] = {
            "status": self.status,
            "kinds": self.kinds,
            "versions": self.versions,
            "issues": list(self.issues),
        }
        if manager is not None:
            report["manager"] = manager
        return report


class CatalogHealth:
    """Validate missing references and gaps in the migration path."""

    def check(self, catalog: GraphCatalog) -> HealthReport:
        """Return every catalog health issue."""
        issues: list[str] = []
        for node in catalog.versions:
            absent = catalog.missing_references(node)
            if absent:
                rendered = ", ".join(
                    f"{kind}@{version}" for kind, version in sorted(absent)
                )
                issues.append(
                    f"{node.jgf_id} references unregistered versions: {rendered}"
                )

        for kind in catalog.entities:
            versions = catalog.kind_versions(kind)
            for source, target in pairwise(versions):
                if not catalog.has_migration(EdgeKey.from_pair(source, target)):
                    issues.append(
                        f"{kind}: missing migration "
                        f"{source.version[1]} -> {target.version[1]}"
                    )

        return HealthReport(
            kinds=len(catalog.entities),
            versions=len(catalog.versions),
            issues=tuple(issues),
        )


__all__ = ["CatalogHealth", "HealthReport"]
