"""JSON Patch migration materializer."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .migration import JsonPatchMigration

if TYPE_CHECKING:
    from pyverge.versioning import Diffable


class JsonPatchMigrationBackend:
    """Materialize a diff as an RFC 6902 JSON Patch migration."""

    def materialize(self, diff: Diffable) -> JsonPatchMigration:
        """Build a declarative migration from the diff."""
        from pyverge.discovery.reflection.render import JsonPatchRenderer  # noqa: PLC0415

        return JsonPatchMigration(
            {
                "from": str(diff.source.version[1]),
                "to": str(diff.target.version[1]),
                "ops": diff.render(JsonPatchRenderer()),
            }
        )


__all__ = ["JsonPatchMigrationBackend"]
