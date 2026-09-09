"""Diff renderers: turn a :class:`Diffable` into an exportable representation."""

from dataclasses import dataclass
from typing import Any, Generic

from .types import Diffable, VersionValue


@dataclass(frozen=True, slots=True)
class JsonPatchRender(Generic[VersionValue]):
    """Render as RFC 6902 JSON Patch.

    Preserves the ``diff`` it was built from, so the renderer can be kept and
    (re)rendered or exported later without losing the patch state.
    """

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
