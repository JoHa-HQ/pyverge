"""Schema-side materialization backend."""

from __future__ import annotations

from pyverge.versioning import Diffable, VersionNode

from .types import ModelAdapter


class ModelMaterializer:
    """Materialize a missing model version from a diff."""

    def __init__(self, adapter: ModelAdapter) -> None:
        self._adapter = adapter

    def materialize(self, diff: Diffable) -> VersionNode:
        """Rebuild the target model and wrap it as a version node."""
        if diff.source.version > diff.target.version:
            diff = diff.inverted()
        model = self._adapter.materialize_model(diff)
        return self._adapter.versionable(model)


__all__ = ["ModelMaterializer"]
