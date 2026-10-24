"""Read-only build graph explorer."""

from __future__ import annotations

from typing import Any, Generic, cast

from pyverge.core.types import VersionValue

from .memory import Registry
from .types import GraphCatalog


class GraphExplorer(Generic[VersionValue]):
    """Build-mode graph queries without constructing a runtime."""

    def __init__(self, catalog: Registry[VersionValue]) -> None:
        self._catalog = catalog

    @property
    def catalog(self) -> Registry[VersionValue]:
        return self._catalog

    def snapshot(self) -> GraphCatalog:
        return cast("GraphCatalog", self._catalog.snapshot())

    def versions(self, kind: str | None = None) -> list[Any]:
        if kind is None:
            return list(self._catalog.versions)
        return list(self._catalog.kind_versions(kind))

    def kinds(self) -> list[str]:
        return list(self._catalog.entities)

    def path(self, source: Any, target: Any) -> list[Any]:
        return self._catalog.migration_path(source, target)


__all__ = ["GraphExplorer"]
