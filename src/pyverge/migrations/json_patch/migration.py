from __future__ import annotations

from typing import Any

from pyverge.versioning import (
    MigrationDescriptor,
    default_canonicalizer,
)

from .patch import JsonPatch


class JsonPatchMigration:
    """Compile a declarative migration spec into a :class:`JsonPatch`.

    The spec's ops are translated to RFC 6902 form once and wrapped in a
    :class:`JsonPatch`. Instances are callable migrations: applying one never
    mutates the input payload.
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
        self.spec = dict(spec)
        self._patch = JsonPatch(self._translate(ops))

    @staticmethod
    def _translate(ops: list[dict[str, Any]]) -> list[dict[str, Any]]:
        translated: list[dict[str, Any]] = []
        for op in ops:
            if op.get("op") in ("move", "copy"):
                translated.append({**op, "path": op["to"]})
            else:
                translated.append(op)
        return translated

    def __call__(
        self,
        data: dict[str, Any],
        context: Any = None,
    ) -> dict[str, Any]:
        return self._patch(data, context)

    @property
    def patch(self) -> JsonPatch:
        """Underlying executable patch used for reflection."""
        return self._patch

    @property
    def migration_identity(self) -> MigrationDescriptor:
        return MigrationDescriptor(
            "jsonpatch",
            default_canonicalizer().dumps(self.spec),
        )
