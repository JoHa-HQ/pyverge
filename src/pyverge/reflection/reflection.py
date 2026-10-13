"""Reflection orchestrator: one diff step, one uniform reflect call.

Both reconstruction call sites (implicit model recovery and explicit migration
proposal) share a single diff-construction step and a single ``reflect`` entry.
Strategy selection is explicit-first: ``MigrationSettings.on_missing`` wins when
it names a reconstruction mode, otherwise the diff's ``origin`` breaks the tie.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Generic

from pyverge.core.types import VersionValue

from .reconstruction import (
    MigrationReflection,
    ModelReflection,
    Reconstruction,
    ReconstructionStrategy,
    strategy_for,
)

if TYPE_CHECKING:
    from pyverge.core.types import MigrationFunc, Versionable
    from pyverge.providers.json_patch import JsonPatch
    from pyverge.providers.types import ModelAdapter
    from pyverge.reflection.diff import Diff
    from pyverge.reflection.discovery import DiffDiscovery


class Reflection(Generic[VersionValue]):
    """Build a diff from either a migration or two schemas, then reflect.

    ``diff`` is the common construction step; ``reflect`` is the uniform entry
    every call site uses.
    """

    def __init__(
        self,
        adapter: ModelAdapter,
        discovery: DiffDiscovery,
        *,
        on_missing: str = "raise",
    ) -> None:
        self._adapter = adapter
        self._discovery = discovery
        self._on_missing = on_missing

    def diff(
        self,
        source: Versionable[VersionValue],
        target: Versionable[VersionValue],
        *,
        migration: JsonPatch | MigrationFunc | None = None,
        is_backward_compatible: bool = False,
    ) -> Diff[VersionValue]:
        """Construct the diff — from a migration (origin ``migration``) or two
        concrete schemas (origin ``schema``)."""
        if migration is not None:
            return self._discovery.discover(migration, source, target)
        return self._adapter.diff(
            source, target, is_backward_compatible=is_backward_compatible
        )

    def strategy(
        self, diff: Diff[VersionValue]
    ) -> ReconstructionStrategy[VersionValue]:
        """Select the strategy: explicit ``on_missing`` first, else by origin."""
        chosen = strategy_for(self._on_missing, adapter=self._adapter)
        if chosen is not None:
            return chosen
        if diff.origin == "migration":
            return ModelReflection(self._adapter)
        return MigrationReflection(self._adapter)

    def reflect(
        self,
        source: Versionable[VersionValue],
        target: Versionable[VersionValue],
        *,
        migration: JsonPatch | MigrationFunc | None = None,
        is_backward_compatible: bool = False,
        strategy: ReconstructionStrategy[VersionValue] | None = None,
    ) -> Reconstruction[VersionValue]:
        """Uniform entry: build the diff, select the strategy, materialize."""
        diff = self.diff(
            source,
            target,
            migration=migration,
            is_backward_compatible=is_backward_compatible,
        )
        active = strategy or self.strategy(diff)
        return active.reflect(diff)
