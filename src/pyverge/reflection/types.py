from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from pyverge.core.types import (
    Comparable,
    MigrationFunc,
    VersionValue,
)
from pyverge.reflection.diff import Diff

MigrationFunc_co = TypeVar("MigrationFunc_co", bound=MigrationFunc, covariant=True)


@runtime_checkable
class DiffDiscovery(Protocol[VersionValue, MigrationFunc_co]):
    """Discover the structural change a migration encodes as a :class:`Diff`.

    Implementations are format-specific: one reads a JSON Patch, another
    parses a Python callable's AST.  The engine selects a strategy per
    migration and uses the resulting :class:`Diff` to reconstruct missing
    model versions.
    """

    def discover(
        self,
        migration: MigrationFunc_co,
        source: Comparable[VersionValue],
        target: Comparable[VersionValue],
    ) -> Diff[VersionValue]: ...
