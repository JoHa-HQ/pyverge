"""Reflection ports."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from pyverge.core.types import MigrationFunc, VersionValue
from pyverge.versioning import Comparable, Diff, Versionable

if TYPE_CHECKING:
    from pyverge.migrations.json_patch import JsonPatch


class DiffProvider(Protocol[VersionValue]):
    """Build a schema diff from a migration or two schemas."""

    def diff(
        self,
        source: Versionable[VersionValue],
        target: Comparable[VersionValue],
        *,
        migration: JsonPatch | MigrationFunc | None = None,
    ) -> Diff[VersionValue]: ...


__all__ = ["DiffProvider"]
