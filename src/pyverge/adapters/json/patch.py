"""Extended JSON Patch operations, pluggable into :class:`jsonpatch.JsonPatch`.

Subclasses :class:`jsonpatch.PatchOperation` so the extended ops
(``set_default``, ``coerce``, ``map``, ``split``) can be registered in a
:class:`jsonpatch.JsonPatch` subclass's ``operations`` mapping and applied in
a single pass alongside the RFC 6902 core ops.
"""

from __future__ import annotations

from typing import Any

import jsonpatch

from pyverge.migration.types import ModelData


class SetDefaultOperation(jsonpatch.PatchOperation):
    """Set a value only if the path is absent."""

    def apply(self, obj: ModelData) -> ModelData:
        if not self.pointer.parts:
            raise jsonpatch.JsonPatchException("Cannot set the document root")
        parent, key = self.pointer.to_last(obj)
        if isinstance(parent, list):
            if key < 0 or key >= len(parent):
                raise jsonpatch.JsonPatchException(f"Array index {key} out of range")
            return obj
        if key not in parent:
            parent[key] = self.operation["value"]
        return obj


class CoerceOperation(jsonpatch.PatchOperation):
    """Convert a value to a target type."""

    def apply(self, obj: ModelData) -> ModelData:
        value = self.pointer.resolve(obj)
        self.pointer.set(obj, self._coerce(value))
        return obj

    def _coerce(self, value: Any) -> Any:
        target = self.operation["type"]
        path = self.operation["path"]
        if target == "string":
            return str(value)
        if target == "boolean":
            return self._coerce_boolean(value, path)
        if target == "integer":
            return self._coerce_integer(value, path)
        if target == "number":
            return self._coerce_number(value, path)
        raise jsonpatch.JsonPatchException(f"Unknown target type {target!r}")

    @staticmethod
    def _coerce_boolean(value: Any, path: str) -> bool:
        if isinstance(value, bool):
            return value
        if value in (1, 0):
            return bool(value)
        if isinstance(value, str):
            if value.lower() == "true":
                return True
            if value.lower() == "false":
                return False
        raise jsonpatch.JsonPatchException(
            f"Cannot coerce {value!r} to boolean at {path}"
        )

    @staticmethod
    def _coerce_integer(value: Any, path: str) -> int:
        if isinstance(value, bool):
            raise jsonpatch.JsonPatchException(
                f"Cannot coerce {value!r} to integer at {path}"
            )
        if isinstance(value, int):
            return value
        if isinstance(value, float) and value.is_integer():
            return int(value)
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                pass
        raise jsonpatch.JsonPatchException(
            f"Cannot coerce {value!r} to integer at {path}"
        )

    @staticmethod
    def _coerce_number(value: Any, path: str) -> int | float:
        if isinstance(value, bool):
            raise jsonpatch.JsonPatchException(
                f"Cannot coerce {value!r} to number at {path}"
            )
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
        raise jsonpatch.JsonPatchException(
            f"Cannot coerce {value!r} to number at {path}"
        )


class MapOperation(jsonpatch.PatchOperation):
    """Remap a value through a mapping, with an optional default."""

    def apply(self, obj: ModelData) -> ModelData:
        value = self.pointer.resolve(obj)
        mapping = self.operation["mapping"]
        if value in mapping:
            self.pointer.set(obj, mapping[value])
            return obj
        if "default" in self.operation:
            self.pointer.set(obj, self.operation["default"])
            return obj
        raise jsonpatch.JsonPatchException(
            f"Value {value!r} not in mapping and no default at {self.operation['path']}"
        )


class SplitOperation(jsonpatch.PatchOperation):
    """Split a string into named fields."""

    def apply(self, obj: ModelData) -> ModelData:
        value = self.pointer.resolve(obj)
        if not isinstance(value, str):
            raise jsonpatch.JsonPatchException(
                f"Expected a string, found {type(value).__name__} at "
                f"{self.operation['path']}"
            )
        parts = value.split(self.operation["sep"])
        for i, field in enumerate(self.operation["fields"]):
            field_pointer = self.pointer_cls(field)
            field_pointer.set(obj, parts[i] if i < len(parts) else None)
        return obj


class JsonPatch(jsonpatch.JsonPatch):
    """RFC 6902 JSON Patch extended with schema-aware ops.

    Registers the extended ops in the ``operations`` mapping so a single
    :meth:`apply` pass handles core and extended ops together.
    """

    operations = jsonpatch.MappingProxyType(
        {
            **jsonpatch.JsonPatch.operations,
            "set_default": SetDefaultOperation,
            "coerce": CoerceOperation,
            "map": MapOperation,
            "split": SplitOperation,
        }
    )
