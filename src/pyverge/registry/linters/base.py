from __future__ import annotations

from typing import Protocol

from pyverge.versioning import Identifiable

from ..types import GraphCatalog, HealthIssue


class HealthLinter(Protocol):
    """Callable health rule applied to one registry entity."""

    def __call__(
        self,
        catalog: GraphCatalog,
        entity: Identifiable,
    ) -> tuple[HealthIssue, ...]: ...


__all__ = ["HealthLinter"]
