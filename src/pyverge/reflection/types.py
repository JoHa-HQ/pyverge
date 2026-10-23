from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pyverge.core.types import (
    Comparable,
    MigrationFunc,
    Versionable,
    VersionValue,
)
from pyverge.reflection.diff import Diff

MigrationFunc_contra = TypeVar(
    "MigrationFunc_contra", bound=MigrationFunc, contravariant=True
)


@runtime_checkable
class DiffDiscovery(Protocol[VersionValue, MigrationFunc_contra]):
    """Discover the structural change a migration encodes as a :class:`Diff`.

    Implementations are format-specific: one reads a JSON Patch, another
    parses a Python callable's AST.  The engine selects a strategy per
    migration and uses the resulting :class:`Diff` to reconstruct missing
    model versions.
    """

    def discover(
        self,
        migration: MigrationFunc_contra,
        source: Versionable[VersionValue],
        target: Comparable[VersionValue],
    ) -> Diff[VersionValue]: ...
