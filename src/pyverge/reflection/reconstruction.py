"""Reconstruction strategies: recover a missing neighbour from a diff.

Two strategies share one shape — a :class:`Reconstruction` outcome carrying
either a rebuilt **model** or a proposed **migration spec**.  A ``Diff`` stays
passive data; the strategy decides which artifact to materialize from it.  The
engine selects the strategy from ``MigrationSettings.on_missing`` (explicit), or
falls back to the diff's ``origin``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic, Protocol, runtime_checkable

from pyverge.core.types import Versionable, VersionValue

if TYPE_CHECKING:
    from pyverge.core.types import Diffable
    from pyverge.providers.json_patch.migration import JsonPatchMigration
    from pyverge.providers.types import ModelAdapter


@dataclass(frozen=True)
class Reconstruction(Generic[VersionValue]):
    """Outcome of a reconstruction strategy.

    Exactly one of *model* (a rebuilt neighbour model) or *migration* (a
    proposed migration spec) is populated, matching the strategy that produced
    it.
    """

    model: Versionable[VersionValue] | None = None
    migration: JsonPatchMigration | None = None


@runtime_checkable
class ReconstructionStrategy(Protocol[VersionValue]):
    """Materialize an artifact from a diff.

    Implementations produce either a rebuilt model or a proposed migration
    spec, depending on the strategy.
    """

    def reflect(self, diff: Diffable[VersionValue]) -> Reconstruction[VersionValue]: ...


class ModelReflection(Generic[VersionValue]):
    """Rebuild a missing model from a diff's anchor and target.

    Inverts the diff when the anchor is the newer endpoint, then materializes
    the model through the provider adapter.  The caller stores it; this
    strategy never mutates the registry.
    """

    def __init__(self, adapter: ModelAdapter) -> None:
        self._adapter = adapter

    def reflect(self, diff: Diffable[VersionValue]) -> Reconstruction[VersionValue]:
        if diff.source.version > diff.target.version:
            diff = diff.inverted()
        model = self._adapter.materialize_model(diff)
        return Reconstruction(model=self._adapter.versionable(model))


class MigrationReflection(Generic[VersionValue]):
    """Propose a migration spec from a diff's source and target schemas.

    Materializes the structural change through the provider adapter into a
    declarative RFC 6902 :class:`JsonPatchMigration`.  Shape-based starting
    point: never auto-registers and never touches endpoint models.
    """

    def __init__(self, adapter: ModelAdapter) -> None:
        self._adapter = adapter

    def reflect(self, diff: Diffable[VersionValue]) -> Reconstruction[VersionValue]:
        return Reconstruction(migration=self._adapter.materialize_migration(diff))


def strategy_for(
    on_missing: str, *, adapter: ModelAdapter
) -> ReconstructionStrategy | None:
    """Select the reconstruction strategy for an ``on_missing`` setting.

    ``"reconstruct_model"`` -> :class:`ModelReflection`;
    ``"reconstruct_migration"`` -> :class:`MigrationReflection`;
    anything else (``"raise"``/``"skip"``) -> ``None`` (no implicit recovery).
    """
    if on_missing == "reconstruct_model":
        return ModelReflection(adapter)
    if on_missing == "reconstruct_migration":
        return MigrationReflection(adapter)
    return None
