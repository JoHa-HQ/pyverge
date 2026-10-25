from __future__ import annotations

from typing import Generic, TypeVar

from pyverge.versioning import Diffable, DiffMaterializer

T = TypeVar("T")


class MigrationMaterializer(Generic[T]):
    """Materialize a migration artifact from a diff using a format backend."""

    def __init__(self, backend: DiffMaterializer[T]) -> None:
        self._backend = backend

    def materialize(self, diff: Diffable) -> T:
        return self._backend.materialize(diff)


__all__ = ["MigrationMaterializer"]
