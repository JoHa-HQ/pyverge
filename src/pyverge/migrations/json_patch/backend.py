from __future__ import annotations

from typing import TYPE_CHECKING

from .migration import JsonPatchMigration

if TYPE_CHECKING:
    from pyverge.versioning import Diffable


class JsonPatchMigrationBackend:
    """Materialize a diff as an RFC 6902 JSON Patch migration."""

    def materialize(self, diff: Diffable) -> JsonPatchMigration:
        from pyverge.discovery.reflection.render import JsonPatchRenderer  # noqa: PLC0415

        return JsonPatchMigration(
            {
                "from": str(diff.source.version),
                "to": str(diff.target.version),
                "ops": diff.render(JsonPatchRenderer()),
            }
        )


__all__ = ["JsonPatchMigrationBackend"]
