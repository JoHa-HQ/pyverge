"""RFC 6902 JSON Patch migration executor, backed by the ``jsonpatch`` library.

A declarative migration is a JSON document::

    {
      "from": "0.1.0",
      "to": "0.2.0",
      "ops": [
        {"op": "add", "path": "/tags", "value": []},
        {"op": "test", "path": "/type", "value": "X"},
        {"op": "move", "from": "/old", "to": "/new"},
        {"op": "map", "path": "/status", "mapping": {"applied": 3, "rejected": 4}}
      ]
    }

Core ops (``add``, ``remove``, ``replace``, ``move``, ``copy``, ``test``) are
delegated to :mod:`jsonpatch`, the reference RFC 6902 implementation.  Extended
ops are schema-aware conveniences layered on top: ``set_default``, ``coerce``,
``map``, ``split``.
"""

from __future__ import annotations

from typing import Any

from pyverge.core.types import ModelData

from .patch import JsonPatch


class JsonPatchMigration:
    """Executes a declarative migration spec over a payload.

    Compiles the spec's ops into a single :class:`JsonPatch` once in the
    constructor; each call applies the whole patch in one pass.  The input
    payload is never mutated — :mod:`jsonpatch` returns a new document.
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

    def __call__(self, data: ModelData) -> ModelData:
        """Apply the whole patch to the payload in one pass."""
        return self._patch.apply(data)
