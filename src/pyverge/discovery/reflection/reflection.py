"""Diff construction from a migration or two schemas.

Materialization is delegated to `DiffMaterializer` backends; this module only
builds the diff.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Generic

from pyverge.core.types import VersionValue

from .types import DiffProvider

if TYPE_CHECKING:
    from pyverge.core.types import MigrationFunc
    from pyverge.discovery.reflection.discovery import DiffDiscovery
    from pyverge.migrations.json_patch import JsonPatch
    from pyverge.schemas.types import ModelAdapter
    from pyverge.versioning import Comparable, Diff, Versionable


class Reflection(DiffProvider[VersionValue], Generic[VersionValue]):
    """Default DiffProvider: build a diff from a migration or two schemas."""

    def __init__(
        self,
        adapter: ModelAdapter,
        discovery: DiffDiscovery,
    ) -> None:
        self._adapter = adapter
        self._discovery = discovery

    def diff(
        self,
        source: Versionable[VersionValue],
        target: Comparable[VersionValue],
        *,
        migration: JsonPatch | MigrationFunc | None = None,
    ) -> Diff[VersionValue]:
        """Construct the diff — from a migration (origin ``migration``) or two
        concrete schemas (origin ``schema``)."""
        if migration is not None:
            return self._discovery.discover(migration, source, target)
        return self._adapter.diff(source, target)
