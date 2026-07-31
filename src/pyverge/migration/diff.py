"""Model version diff: pure data with queryable predicates and pluggable rendering."""

from dataclasses import dataclass, field
from typing import Any, Generic, Self

from pydantic_core import PydanticUndefined

from .types import (
    Diffable,
    MigrationKey,
    Renderable,
    Versionable,
    VersionValue,
    VSource,
    VTarget,
)


@dataclass(frozen=True)
class JsonPatchRender(Generic[VersionValue]):
    """Render as RFC 6902 JSON Patch."""

    diff: Diffable[VersionValue]
    format: str = "json-patch"

    def __call__(self) -> list[dict[str, Any]]:
        return self.render(self.diff)

    def render(self, diff: Diffable[VersionValue]) -> list[dict[str, Any]]:
        ops: list[dict[str, Any]] = []
        for _field in diff.added_fields:
            default = diff.added_default(_field)
            ops.append({"op": "add", "path": f"/{_field}", "value": default})
        for _field in diff.removed_fields:
            ops.append({"op": "remove", "path": f"/{_field}"})
        for _field, changes in diff.modified_fields.items():
            op: dict[str, Any] = {
                "op": "replace",
                "path": f"/{_field}",
                "changes": changes,
            }
            if "type_changed" in changes:
                op["value"] = None
            if (
                "required_changed" in changes
                and not changes["required_changed"]["from"]
            ):
                op["value"] = None
            ops.append(op)
        return ops


@dataclass(frozen=True)
class PydanticDiff(Generic[VersionValue, VSource, VTarget]):
    """Differences between two model versions — data with queryable predicates.

    Computed eagerly from two Pydantic model classes.  No migration logic —
    callers query the diff to decide what to do.  Render output via the
    pluggable ``renderer`` strategy.
    """

    source: Versionable[VersionValue, VSource]
    target: Versionable[VersionValue, VTarget]
    added_fields: list[str] = field(default_factory=list)
    removed_fields: list[str] = field(default_factory=list)
    modified_fields: dict[str, dict[str, Any]] = field(default_factory=dict)
    added_field_info: dict[str, dict[str, Any]] = field(default_factory=dict)
    unchanged_fields: list[str] = field(default_factory=list)
    renderer: type[Renderable] = field(default=JsonPatchRender)
    is_backward_compatible: bool = False

    @classmethod
    def from_pair(
        cls: type[Self],
        source: Versionable[VersionValue, VSource],
        target: Versionable[VersionValue, VTarget],
        *,
        is_backward_compatible: bool = False,
    ) -> Self:
        """Create by comparing field metadata of two Pydantic models."""
        if source.strategy != target.strategy:
            raise ValueError(
                f"Cannot create diff across strategies: "
                f"{source.strategy.__name__} != {target.strategy.__name__}"
            )

        if source.kind != target.kind:
            raise ValueError(
                f"Cannot create diff across kinds: {source.kind} != {target.kind}"
            )

        source_fields = source.model.model_fields
        target_fields = target.model.model_fields

        source_keys = set(source_fields.keys())
        target_keys = set(target_fields.keys())

        added = sorted(target_keys - source_keys)
        removed = sorted(source_keys - target_keys)
        common = source_keys & target_keys

        modified: dict[str, dict[str, Any]] = {}
        unchanged: list[str] = []

        for fn in sorted(common):
            sf = source_fields[fn]
            tf = target_fields[fn]
            changes = cls._diff_fields(sf, tf)
            if changes:
                modified[fn] = changes
            else:
                unchanged.append(fn)

        added_info = {}
        for fn in added:
            tf = target_fields[fn]
            added_info[fn] = {
                "type": tf.annotation,
                "required": tf.is_required(),
                "default": tf.default if tf.default is not PydanticUndefined else None,
            }

        return cls(
            source=source,
            target=target,
            added_fields=added,
            removed_fields=removed,
            modified_fields=modified,
            added_field_info=added_info,
            unchanged_fields=unchanged,
            is_backward_compatible=is_backward_compatible,
        )

    @staticmethod
    def _diff_fields(source: Any, target: Any) -> dict[str, Any]:
        changes: dict[str, Any] = {}

        if source.annotation != target.annotation:
            changes["type_changed"] = {
                "from": source.annotation,
                "to": target.annotation,
            }

        from_req = source.is_required()
        to_req = target.is_required()
        if from_req != to_req:
            changes["required_changed"] = {"from": from_req, "to": to_req}

        from_def = source.default
        to_def = target.default
        if from_def != to_def and not (
            from_def is PydanticUndefined and to_def is PydanticUndefined
        ):
            if from_def is not PydanticUndefined and to_def is not PydanticUndefined:
                changes["default_changed"] = {"from": from_def, "to": to_def}
            elif from_def is PydanticUndefined:
                changes["default_added"] = to_def
            else:
                changes["default_removed"] = from_def

        return changes

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

    def render(self) -> Renderable:
        """Render this diff using the configured strategy."""
        return self.renderer(self)
