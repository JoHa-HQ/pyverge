"""FastMCP primitive adapters.

Each :class:`ComponentKind` is the anti-corruption layer for one FastMCP
primitive family. It lists host components, normalizes them into domain
:class:`~.domain.Entrance` values, and materializes a domain
:class:`~.domain.VirtualComponent` back into a FastMCP primitive.

The provider depends only on the :class:`ComponentKind` port, so a new primitive
family is a new adapter rather than a provider change.
"""

from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any, ClassVar

from fastmcp.prompts.base import PromptArgument
from fastmcp.prompts.function_prompt import FunctionPrompt
from fastmcp.resources.template import FunctionResourceTemplate
from fastmcp.tools.function_tool import FunctionTool

from .domain import (
    Entrance,
    Policy,
    PolicyValue,
    VersionRange,
    VirtualComponent,
)
from .ports import ComponentKind

if TYPE_CHECKING:
    from fastmcp import FastMCP


class _FastMCPKind(ABC):
    """Template for the shared FastMCP-to-domain normalization."""

    name: ClassVar[str]

    @abstractmethod
    def components(self, server: FastMCP) -> AsyncIterator[Any]:
        """Yield every component of this family on *server*."""

    @abstractmethod
    def materialize(self, server: FastMCP, virtual: VirtualComponent) -> Any:
        """Create the host primitive for *virtual*."""

    @abstractmethod
    def _schema(self, component: Any) -> dict[str, Any]:
        """Return the JSON-schema view of *component*."""

    def kind(self, component: Any) -> str:
        return str(component.name)

    def version(self, component: Any) -> str | None:
        version = getattr(component, "version", None)
        return None if version is None else str(version)

    @staticmethod
    def _fields(schema: dict[str, Any]) -> list[str]:
        """Return the property names of *schema*."""
        return list(schema.get("properties", {}))

    @staticmethod
    def _signature(
        fn: Callable[..., Any],
        names: list[str],
        *,
        required_first: bool,
    ) -> Callable[..., Any]:
        """Return *fn* wrapped with an explicit FastMCP-visible signature."""

        def indirection(**kwargs: Any) -> Any:
            return fn(**kwargs)

        indirection.__name__ = getattr(fn, "__name__", "indirection")
        setattr(
            indirection,
            "__signature__",
            inspect.Signature(
                [
                    inspect.Parameter(
                        name,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        default=(
                            inspect.Parameter.empty
                            if required_first and index == 0
                            else None
                        ),
                    )
                    for index, name in enumerate(names)
                ]
            ),
        )
        return indirection

    @staticmethod
    def _policy_value(value: Any) -> PolicyValue | None:
        """Coerce one JSON policy value, including a range object."""
        if isinstance(value, str):
            return value
        if (
            isinstance(value, dict)
            and value
            and set(value) <= {"gte", "lt", "eq"}
            and all(isinstance(item, str) for item in value.values())
        ):
            return VersionRange(
                gte=value.get("gte"),
                lt=value.get("lt"),
                eq=value.get("eq"),
            )
        return None

    def policy(self, component: Any) -> Policy | None:
        """Return the policy declared in a component's ``meta``, if valid."""
        meta = getattr(component, "meta", None)
        if not isinstance(meta, dict):
            return None
        declared = meta.get("policy")
        if not isinstance(declared, dict):
            return self._policy_value(declared)
        scalar = self._policy_value(declared)
        if scalar is not None:
            return scalar
        mapping: dict[str, PolicyValue] = {}
        for key, value in declared.items():
            item = self._policy_value(value)
            if not isinstance(key, str) or item is None:
                return None
            mapping[key] = item
        return mapping

    def handler(self, component: Any) -> Callable[..., Any] | None:
        """Return the callable behind a FastMCP component."""
        return getattr(component, "fn", None) or getattr(component, "run", None)

    def entrance(
        self,
        component: Any,
        *,
        policy: Policy | None = None,
        explicit: bool = False,
    ) -> Entrance | None:
        """Bind *component* to a graph entrance, or ``None`` if unversioned.

        Args:
            component: FastMCP primitive.
            policy: Fallback policy when the component declares none.
            explicit: Whether the component was registered on the provider.

        Returns:
            Entrance | None: The bound entrance, or ``None`` for an unversioned
                component.

        Raises:
            ValueError: If neither the component nor *policy* declares one.
        """
        version = self.version(component)
        if version is None:
            return None
        kind = self.kind(component)
        resolved = self.policy(component) or policy
        if resolved is None:
            raise ValueError(
                f"versioned primitive {kind!r} has no policy; declare "
                "meta={'policy': ...} or record one in the provider policies"
            )
        return Entrance(
            source=self.name,
            kind=kind,
            version=version,
            schema=self._schema(component),
            handler=self.handler(component),
            policy=resolved,
            explicit=explicit,
        )


class ToolKind(_FastMCPKind):
    """Tools: ``parameters`` is the schema, ``add_tool`` materializes."""

    name = "tool"

    async def components(self, server: FastMCP) -> AsyncIterator[Any]:
        for tool in await server.list_tools():
            yield tool

    def _schema(self, component: Any) -> dict[str, Any]:
        return dict(component.parameters)

    def materialize(self, server: FastMCP, virtual: VirtualComponent) -> Any:
        return server.add_tool(
            FunctionTool(
                name=virtual.kind,
                version=virtual.version,
                parameters=virtual.schema,
                fn=virtual.handler,
            )
        )


class PromptKind(_FastMCPKind):
    """Prompts: arguments become an object schema, ``add_prompt`` materializes."""

    name = "prompt"

    async def components(self, server: FastMCP) -> AsyncIterator[Any]:
        for prompt in await server.list_prompts():
            yield prompt

    def _schema(self, component: Any) -> dict[str, Any]:
        properties: dict[str, Any] = {}
        required: list[str] = []
        for argument in component.arguments or []:
            prop: dict[str, Any] = {"type": "string"}
            if argument.description:
                prop["description"] = argument.description
            properties[argument.name] = prop
            if argument.required:
                required.append(argument.name)
        document: dict[str, Any] = {"type": "object", "properties": properties}
        if required:
            document["required"] = required
        return document

    def materialize(self, server: FastMCP, virtual: VirtualComponent) -> Any:
        prompt = FunctionPrompt.from_function(
            self._signature(
                virtual.handler,
                self._fields(virtual.schema),
                required_first=False,
            ),
            name=virtual.kind,
            version=virtual.version,
        )
        # The factory derives arguments from the handler signature; the graph
        # schema is the contract, so it replaces them.
        prompt.arguments = [
            PromptArgument(
                name=name,
                description=prop.get("description"),
                required=name in virtual.schema.get("required", []),
            )
            for name, prop in virtual.schema.get("properties", {}).items()
        ]
        return server.add_prompt(prompt)


class ResourceKind(_FastMCPKind):
    """Resources and templates: ``parameters`` is the schema.

    ``uri_scheme`` prefixes virtual templates so they match the physical ones.
    """

    name = "resource"

    def __init__(self, *, uri_scheme: str = "") -> None:
        self._uri_scheme = uri_scheme

    async def components(self, server: FastMCP) -> AsyncIterator[Any]:
        for resource in await server.list_resources():
            yield resource
        for template in await server.list_resource_templates():
            yield template

    def kind(self, component: Any) -> str:
        name = component.name
        if name:
            return str(name)
        return str(
            getattr(component, "uri_template", None) or getattr(component, "uri", None)
        )

    def _schema(self, component: Any) -> dict[str, Any]:
        parameters = getattr(component, "parameters", None)
        return dict(parameters) if parameters else {"type": "object"}

    def _uri_template(self, kind: str, schema: dict[str, Any]) -> str:
        names = self._fields(schema)
        if not names:
            raise ValueError(f"kind {kind!r} has no properties for a URI template")
        prefix = self._uri_scheme or f"{kind}/"
        template = f"{prefix}{{{names[0]}}}"
        rest = names[1:]
        if rest:
            template += "{?" + ",".join(rest) + "}"
        return template

    def materialize(self, server: FastMCP, virtual: VirtualComponent) -> Any:
        template = FunctionResourceTemplate.from_function(
            self._signature(
                virtual.handler,
                self._fields(virtual.schema),
                required_first=True,
            ),
            uri_template=self._uri_template(virtual.kind, virtual.schema),
            name=virtual.kind,
            version=virtual.version,
        )
        # The factory derives parameters from the handler signature; the graph
        # schema is the contract, so it replaces them.
        template.parameters = virtual.schema
        return server.add_template(template)


DEFAULT_KINDS: tuple[ComponentKind, ...] = (
    ToolKind(),
    PromptKind(),
    ResourceKind(),
)

__all__ = [
    "DEFAULT_KINDS",
    "PromptKind",
    "ResourceKind",
    "ToolKind",
]
