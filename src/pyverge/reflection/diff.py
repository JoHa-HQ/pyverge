"""Model version diff: pure data with queryable predicates and pluggable rendering."""

from dataclasses import dataclass, field
from typing import Any, Generic, Self

from pyverge.core.render import JsonPatchRender
from pyverge.core.types import (
    MigrationKey,
    Renderable,
    Versionable,
    VersionValue,
    VSource_co,
    VTarget_co,
)


@dataclass(frozen=True)
class Diff(Generic[VersionValue, VSource_co, VTarget_co]):
    """Differences between two model versions — data with queryable predicates.

    Provider-agnostic.  Provider-specific construction (e.g.
    :class:`PydanticDiff.from_pair`) computes the predicate data and returns a
    ``Diff``.  A meta version (an endpoint with no concrete model) is a plain
    ``Diff`` with empty predicates.
    """

    source: Versionable[VersionValue, VSource_co]
    target: Versionable[VersionValue, VTarget_co]
    added_fields: list[str] = field(default_factory=list)
    removed_fields: list[str] = field(default_factory=list)
    modified_fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    added_field_info: dict[str, dict[str, Any]] = field(default_factory=dict)
    unchanged_fields: list[str] = field(default_factory=list)
    renderer: type[JsonPatchRender] = field(default=JsonPatchRender)
    is_backward_compatible: bool = False

    @property
    def kind(self) -> str:
        return self.source.kind

    @property
    def edge(self) -> MigrationKey:
        return (self.source, self.target)

    @property
    def is_backward(self) -> bool:
        return self.source > self.target

    @property
    def is_forward(self) -> bool:
        return self.source < self.target

    @property
    def is_identity(self) -> bool:
        return (
            not self.added_fields
            and not self.removed_fields
            and not self.modified_fields
        )

    @property
    def has_additions(self) -> bool:
        return bool(self.added_fields)

    @property
    def has_removals(self) -> bool:
        return bool(self.removed_fields)

    @property
    def has_modifications(self) -> bool:
        return bool(self.modified_fields)

    @property
    def has_type_changes(self) -> bool:
        return any("type_changed" in c for c in self.modified_fields.values())

    @property
    def has_constraint_changes(self) -> bool:
        return any("required_changed" in c for c in self.modified_fields.values())

    def is_added(self, field: str) -> bool:
        return field in self.added_fields

    def is_removed(self, field: str) -> bool:
        return field in self.removed_fields

    def is_modified(self, field: str) -> bool:
        return field in self.modified_fields

    def is_added_required(self, field: str) -> bool:
        info = self.added_field_info.get(field)
        return bool(info and info.get("required"))

    def added_default(self, field: str) -> Any:
        info = self.added_field_info.get(field)
        return info.get("default") if info else None

    def modified_change(self, field: str, key: str) -> Any | None:
        return self.modified_fields.get(field, {}).get(key)

    def is_union_expansion(self, field: str) -> bool:
        rc = self.modified_change(field, "required_changed")
        return rc is not None and rc["from"] and not rc["to"]

    def is_union_contraction(self, field: str) -> bool:
        rc = self.modified_change(field, "required_changed")
        return rc is not None and not rc["from"] and rc["to"]

    @property
    def render(self) -> Renderable:
        """Render this diff using the configured strategy."""
        return self.renderer(self)

    def inverted(self) -> Self:
        """Return the inverse diff: added/removed fields swap.

        Used to reconstruct a version from an anchor when the migration edge
        points the other way (e.g. reconstructing v1 from a v2 anchor via the
        v1→v2 migration).
        """
        return Diff(
            source=self.source,
            target=self.target,
            added_fields=list(self.removed_fields),
            removed_fields=list(self.added_fields),
            modified_fields=dict(self.modified_fields),
            added_field_info=dict(self.added_field_info),
            unchanged_fields=list(self.unchanged_fields),
            renderer=self.renderer,
            is_backward_compatible=self.is_backward_compatible,
        )
