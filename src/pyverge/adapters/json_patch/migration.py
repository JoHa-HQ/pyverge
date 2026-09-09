"""Declarative JSON Patch migration spec adapter.

Compile a declarative spec document into an executable RFC 6902
:class:`JsonPatch`.  :class:`JsonPatchMigration` is a migration-format
adapter: it builds a :class:`JsonPatch` — the actual migration function — and
is itself not callable.
"""

from __future__ import annotations

from typing import Any

from .patch import JsonPatch


class JsonPatchMigration:
    """Compile a declarative migration spec into a :class:`JsonPatch`.

    The spec's ops are translated to RFC 6902 form once and wrapped in a
    :class:`JsonPatch`.  The resulting patch (``.patch``) is the executable
    migration: applying it never mutates the input payload.
    """

    def __init__(self, spec: dict[str, Any]) -> None:
        if not isinstance(spec, dict):
            raise ValueError("Migration spec must be a JSON object")
        for key in ("from", "to"):
            if not isinstance(spec.get(key), str) or not spec[key]:
                raise ValueError(
                    f"Migration spec requires a non-empty '{key}' version string"
                )
        ops = spec.get("ops")
        if not isinstance(ops, list) or not ops:
            raise ValueError("Migration spec requires a non-empty 'ops' list")
        self._patch = JsonPatch(self._translate(ops))

    @staticmethod
    def _translate(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Translate spec ops for :mod:`jsonpatch`.

        ``jsonpatch`` names the move/copy target ``path``; the migration spec
        uses ``to``.
        """
        translated: list[dict[str, Any]] = []
        for op in ops:
            if op.get("op") in ("move", "copy"):
                translated.append({**op, "path": op["to"]})
            else:
                translated.append(op)
        return translated

    @property
    def patch(self) -> JsonPatch:
        """The compiled executable JSON Patch."""
        return self._patch
