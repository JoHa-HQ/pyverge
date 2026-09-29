"""Schema reflection — wrap a reflected schema document as a versionable.

FastMCP reflects a tool's input schema (or a prompt's arguments) into a JSON
Schema document. This helper turns that document into a pyverge model: it drops
injected parameters (wiring, not payload) and injects the ``kind``/``version``
identity fields, then wraps the result through the manager's model adapter.

Adapter-local: it needs both the reflected document and the model adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyverge.types import ModelAdapter, Versionable

#: Identity fields owned by the version graph, not the caller.
IDENTITY = ("kind", "version")


@dataclass(frozen=True)
class SchemaReflection:
    """A reflected schema document, ready to become a versioned model."""

    adapter: ModelAdapter
    kind: str
    version: str
    schema: dict[str, Any]
    injected: frozenset[str] = field(default_factory=frozenset)

    def compliant(self) -> dict[str, Any]:
        """Return the schema with injected params dropped and identity injected."""
        document = {**self.schema}
        properties = dict(document.get("properties", {}))
        for name in self.injected:
            properties.pop(name, None)
        for name, default in zip(IDENTITY, (self.kind, self.version), strict=True):
            properties.setdefault(name, {"type": "string", "default": default})
        document["properties"] = properties
        required = document.get("required")
        if required:
            document["required"] = [r for r in required if r not in self.injected]
        return document

    def versionable(self) -> Versionable:
        """Wrap the compliant schema into a versionable via the adapter.

        The schema document is passed as the "model"; a schema-based adapter
        materializes it, a typed adapter may refuse it (the host then relies on
        an already-registered model).
        """
        document = self.compliant()
        return self.adapter.versionable(
            document,  # ty: ignore[invalid-argument-type]
            kind=self.kind,
            version=self.version,
        )


__all__ = ["IDENTITY", "SchemaReflection"]
