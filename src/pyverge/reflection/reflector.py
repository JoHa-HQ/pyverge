"""Build-time reflection: diff construction and artifact materialization."""

from __future__ import annotations

from typing import Any, Generic

from pyverge.core.types import MigrationFunc, VersionValue
from pyverge.migrations.json_patch import JsonPatch
from pyverge.reflection.types import DiffProvider
from pyverge.registry.errors import CatalogError, ModelNotFoundError
from pyverge.schemas.types import ModelAdapter
from pyverge.versioning import Comparable, DiffMaterializer, VersionNode


class Reflector(Generic[VersionValue]):
    """Build diffs and materialize missing models or proposed migrations."""

    def __init__(
        self,
        adapter: ModelAdapter,
        diff_provider: DiffProvider[VersionValue],
        materializers: dict[str, DiffMaterializer[Any]],
        *,
        on_missing: str = "raise",
    ) -> None:
        self._adapter = adapter
        self._diff_provider = diff_provider
        self._materializers = materializers
        self._on_missing = on_missing

    def diff(
        self,
        source: Any,
        target: Any,
        *,
        migration: JsonPatch | MigrationFunc | None = None,
    ) -> Any:
        return self._diff_provider.diff(source, target, migration=migration)

    def materialize_missing(
        self,
        anchor: VersionNode[VersionValue],
        target: Comparable[VersionValue],
        func: MigrationFunc,
    ) -> VersionNode[VersionValue]:
        if (
            self._on_missing != "reconstruct_model"
            or "reconstruct_model" not in self._materializers
        ):
            raise ModelNotFoundError("registry", target.version)
        diff = self.diff(anchor, target, migration=func)
        node = self._materializers["reconstruct_model"].materialize(diff)
        if not isinstance(node, VersionNode):
            raise ModelNotFoundError("registry", target.version)
        return node

    def propose(
        self,
        source: VersionNode[VersionValue],
        target: VersionNode[VersionValue],
    ) -> Any:
        if source.kind != target.kind:
            raise CatalogError(
                "registry",
                f"Cannot propose migration across kinds: "
                f"{source.kind} != {target.kind}",
            )
        if source.strategy != target.strategy:
            raise CatalogError(
                "registry",
                f"Cannot propose migration across strategies: "
                f"{source.strategy.__name__} != {target.strategy.__name__}",
            )
        diff = self.diff(source, target)
        return self._materializers["reconstruct_migration"].materialize(diff)


__all__ = ["Reflector"]
