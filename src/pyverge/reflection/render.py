"""Schema diff renderers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Generic

from pyverge.core.types import VersionValue
from pyverge.versioning import Diffable


@dataclass(frozen=True, slots=True)
class JsonPatchRenderer(Generic[VersionValue]):
    """Render a diff as RFC 6902 JSON Patch."""

    format: str = "json-patch"

    def render(self, diff: Diffable[VersionValue]) -> list[dict[str, Any]]:
        """Render *diff* as JSON Patch operations."""
        ops: list[dict[str, Any]] = []
        for field in diff.added_fields:
            default = diff.added_default(field)
            ops.append({"op": "add", "path": f"/{field}", "value": default})
        for field in diff.removed_fields:
            ops.append({"op": "remove", "path": f"/{field}"})
        for field, changes in diff.modified_fields.items():
            op: dict[str, Any] = {
                "op": "replace",
                "path": f"/{field}",
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

    def __call__(self, diff: Diffable[VersionValue]) -> list[dict[str, Any]]:
        """Callable shorthand for :meth:`render`."""
        return self.render(diff)


__all__ = ["JsonPatchRenderer"]
