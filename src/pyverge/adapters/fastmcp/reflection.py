"""Per-component reflectors — pure ``(component, adapter) -> compliant model``.

Contrast with :class:`~pyverge.adapters.fastmcp.registry.ToolRegistry`, which
owns the server-wide lifecycle (search / register / enrich).  A reflector is
registry-free: it takes a single FastMCP component (tool, prompt, resource or
resource template) and a pyverge model adapter, and returns the *compliant*
shape for that component — a JSON Schema document with ``kind``/``version``
defaults injected, ready to wrap through ``adapter.versionable``.

Three reflectors share the :class:`ComponentReflection` contract and differ
only in how they synthesize the schema document:

* :class:`ToolReflection` — a FastMCP ``Tool`` whose ``parameters`` is already
  a JSON Schema document,
* :class:`PromptReflection` — a FastMCP ``Prompt`` whose ``arguments`` are
  typed ``PromptArgument`` lists (no JSON Schema), synthesized into one,
* :class:`ResourceReflection` — a FastMCP ``Resource`` (no parameters → empty
  object schema) or ``ResourceTemplate`` (``parameters`` JSON Schema).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class ComponentReflection(ABC):
    """Reflect a single FastMCP component into its compliant schema.

    Subclasses only implement :meth:`kind` and :meth:`schema`; the shared
    contract (component access, version, identity injection, ``versionable``
    wrapping) lives here.
    """

    def __init__(self, component, adapter) -> None:
        self._component = component
        self._adapter = adapter

    @property
    def component(self) -> Any:
        return self._component

    @property
    @abstractmethod
    def kind(self) -> str:
        """The component's kind (identity key for the model adapter)."""

    @property
    def version(self) -> str | None:
        if self._component.version is None:
            return None
        return str(self._component.version)

    @abstractmethod
    def schema(self) -> dict[str, Any]:
        """Return the component's compliant schema document."""

    def _inject_identity(self, document: dict[str, Any]) -> dict[str, Any]:
        """Return *document* with ``kind``/``version`` default properties injected.

        The model materialized from the document must round-trip its identity
        through fields (mirroring the registered raw models), so the adapter can
        read ``kind``/``version`` back when wrapping it.
        """
        assert self.version is not None
        props = document.setdefault("properties", {})
        for name, default in zip(
            ("kind", "version"), (self.kind, self.version), strict=True
        ):
            props.setdefault(name, {"type": "string", "default": default})
        return document

    def versionable(self) -> Any:
        """Wrap the component's compliant schema into a versionable."""
        return self._adapter.versionable(
            self.schema(), kind=self.kind, version=self.version
        )

    def __repr__(self) -> str:
        return f"{type(self).__name__}(kind={self.kind!r}, version={self.version!r})"


class ToolReflection(ComponentReflection):
    """Reflect a single FastMCP :class:`Tool` into its compliant schema."""

    @property
    def kind(self) -> str:
        return self._component.name

    def schema(self) -> dict[str, Any]:
        """Return the tool's parameters as a compliant schema document."""
        version = self.version
        if version is None:
            raise ValueError(f"tool {self._component.name!r} is not versioned")
        return self._inject_identity(dict(self._component.parameters))


class PromptReflection(ComponentReflection):
    """Reflect a single FastMCP :class:`Prompt` into its compliant schema.

    A prompt's ``arguments`` are ``PromptArgument`` records (name/description/
    required), not a JSON Schema — the reflector synthesizes an object schema
    whose properties are strings.
    """

    @property
    def kind(self) -> str:
        return self._component.name

    def schema(self) -> dict[str, Any]:
        """Synthesize a compliant schema document from the prompt arguments."""
        version = self.version
        if version is None:
            raise ValueError(f"prompt {self._component.name!r} is not versioned")
        props: dict[str, Any] = {}
        required: list[str] = []
        for arg in self._component.arguments or []:
            prop: dict[str, Any] = {"type": "string"}
            if arg.description:
                prop["description"] = arg.description
            props[arg.name] = prop
            if arg.required:
                required.append(arg.name)
        document: dict[str, Any] = {"type": "object", "properties": props}
        if required:
            document["required"] = required
        return self._inject_identity(document)


class ResourceReflection(ComponentReflection):
    """Reflect a single FastMCP resource into its compliant schema.

    A static :class:`Resource` has no parameters, so its compliant schema is
    an empty object (identity fields only).  A :class:`ResourceTemplate`
    carries a full ``parameters`` JSON Schema, used as-is.
    """

    @property
    def kind(self) -> str:
        name = self._component.name
        if name:
            return name
        uri = getattr(self._component, "uri_template", None)
        if uri:
            return str(uri)
        return str(self._component.uri)

    def schema(self) -> dict[str, Any]:
        """Return the resource's compliant schema document."""
        version = self.version
        if version is None:
            raise ValueError(f"resource {self.kind!r} is not versioned")
        parameters = getattr(self._component, "parameters", None)
        document: dict[str, Any] = (
            dict(parameters) if parameters else {"type": "object"}
        )
        document.setdefault("properties", {})
        return self._inject_identity(document)


__all__ = [
    "ComponentReflection",
    "PromptReflection",
    "ResourceReflection",
    "ToolReflection",
]
