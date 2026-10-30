from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Generic, cast

from pyverge.core.types import Attachable, VersionValue
from pyverge.graph.types import MigrationDefinition
from pyverge.registry.errors import MigrationNotFoundError
from pyverge.registry.types import GraphCatalog
from pyverge.versioning import EdgeKey


@dataclass(frozen=True, slots=True)
class MigrationBindings(Generic[VersionValue]):
    """Immutable execution-side bindings resolved from a mutable catalog."""

    name: str
    definitions: Mapping[EdgeKey, MigrationDefinition[VersionValue]]
    hooks_by_edge: Mapping[EdgeKey, tuple[Attachable, ...]]

    @classmethod
    def from_catalog(
        cls, catalog: GraphCatalog[VersionValue]
    ) -> MigrationBindings[VersionValue]:
        definitions: dict[EdgeKey, MigrationDefinition[VersionValue]] = {}
        hooks_by_edge: dict[EdgeKey, tuple[Attachable, ...]] = {}
        for kind in catalog.kinds:
            for edge in catalog.migrations(kind):
                key = EdgeKey.from_pair(edge.source, edge.target)
                definitions[key] = cast("MigrationDefinition[VersionValue]", edge)
            for edge in catalog.edges(kind):
                key = EdgeKey.from_pair(edge.source, edge.target)
                hooks = catalog.get_hooks(key)
                if hooks:
                    hooks_by_edge[key] = tuple(hooks)
        return cls(
            name=catalog.name,
            definitions=MappingProxyType(definitions),
            hooks_by_edge=MappingProxyType(hooks_by_edge),
        )

    def resolve(self, key: EdgeKey[VersionValue]) -> MigrationDefinition[VersionValue]:
        try:
            return self.definitions[key]
        except KeyError:
            raise MigrationNotFoundError(self.name, key.key) from None

    def hooks(self, key: EdgeKey[VersionValue]) -> Sequence[Attachable]:
        return self.hooks_by_edge.get(key, ())


__all__ = ["MigrationBindings"]
