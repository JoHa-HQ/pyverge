"""Component reflectors — adapt a FastMCP component to :class:`SchemaReflection`.

A FastMCP tool carries its input schema directly; a prompt's arguments and a
resource's parameters must be synthesized into one. Each reflector only turns
the component into a schema document; the schema→versionable work is
framework-agnostic and lives in :mod:`pyverge.serving.reflection`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pyverge.serving import SchemaReflection, injected_names


class ComponentReflection(ABC):
    """Reflect a FastMCP component into a :class:`SchemaReflection`."""

    def __init__(self, component, adapter, *, injected: set[str] | None = None) -> None:
        self._component = component
        self._adapter = adapter
        self._injected = injected

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
        """Return the component's input schema document."""

    def _injected_names(self) -> frozenset[str]:
        if self._injected is not None:
            return frozenset(self._injected)
        fn = getattr(self._component, "fn", None)
        return frozenset(injected_names(fn)) if fn is not None else frozenset()

    def _require_version(self, label: str) -> str:
        version = self.version
        if version is None:
            raise ValueError(f"{label} {self._component.name!r} is not versioned")
        return version

    def reflection(self) -> SchemaReflection:
        """Return the framework-agnostic reflection for this component."""
        return SchemaReflection(
            self._adapter,
            kind=self.kind,
            version=self._require_version(type(self).__name__),
            schema=self.schema(),
            injected=self._injected_names(),
        )

    def versionable(self) -> Any:
        return self.reflection().versionable()

    def __repr__(self) -> str:
        return f"{type(self).__name__}(kind={self.kind!r}, version={self.version!r})"


class ToolReflection(ComponentReflection):
    """Reflect a FastMCP :class:`Tool` (its ``parameters`` schema)."""

    @property
    def kind(self) -> str:
        return self._component.name

    def schema(self) -> dict[str, Any]:
        self._require_version("tool")
        return dict(self._component.parameters)


class PromptReflection(ComponentReflection):
    """Reflect a FastMCP :class:`Prompt` into an object schema of string args."""

    @property
    def kind(self) -> str:
        return self._component.name

    def schema(self) -> dict[str, Any]:
        self._require_version("prompt")
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
        return document


class ResourceReflection(ComponentReflection):
    """Reflect a FastMCP resource/template (its ``parameters`` schema)."""

    @property
    def kind(self) -> str:
        name = self._component.name
        if name:
            return name
        uri = getattr(self._component, "uri_template", None)
        return str(uri) if uri else str(self._component.uri)

    def schema(self) -> dict[str, Any]:
        self._require_version("resource")
        parameters = getattr(self._component, "parameters", None)
        return dict(parameters) if parameters else {"type": "object"}


__all__ = [
    "ComponentReflection",
    "PromptReflection",
    "ResourceReflection",
    "ToolReflection",
]
