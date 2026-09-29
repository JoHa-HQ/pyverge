from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeAlias

from fastmcp.prompts.base import PromptArgument
from fastmcp.prompts.function_prompt import FunctionPrompt
from fastmcp.resources.template import FunctionResourceTemplate
from fastmcp.tools.function_tool import FunctionTool

from pyverge.core import VersionNode
from pyverge.types import ModelAdapter, Versionable

from .injection import InjectionDetector, injected_names

if TYPE_CHECKING:
    from fastmcp import FastMCP

#: A policy declared in a primitive's ``meta`` — the JSON-representable subset of
#: a pyverge target policy: a named/pinned version, or a per-kind mapping.
Policy: TypeAlias = str | dict[str, str]


@dataclass(frozen=True)
class ReflectedNode:
    """A versioned primitive, normalized for the version graph.

    Bridges the reflected schema to a versionable: drops injected (wired)
    parameters, injects the identity fields, and wraps the result through the
    provider's adapter.
    """

    provider: ComponentReflection
    kind: str
    version: str
    schema: dict[str, Any]
    injected: frozenset[str]
    handler: Callable[..., Any] | None
    policy: Policy | None = None

    def _identity(self) -> tuple[str, str]:
        adapter = self.provider.adapter
        return adapter.kind_property, adapter.version_property

    def compliant(self) -> dict[str, Any]:
        """Schema with injected params dropped and identity fields injected."""
        document = {**self.schema}
        properties = dict(document.get("properties", {}))
        for name in self.injected:
            properties.pop(name, None)
        for name, default in zip(
            self._identity(), (self.kind, self.version), strict=True
        ):
            properties.setdefault(name, {"type": "string", "default": default})
        document["properties"] = properties
        required = document.get("required")
        if required:
            document["required"] = [r for r in required if r not in self.injected]
        return document

    def fields(self) -> frozenset[str]:
        """Payload fields, minus the identity fields."""
        identity = set(self._identity())
        return frozenset(set(self.compliant().get("properties", {})) - identity)

    def versionable(self) -> Versionable:
        """Wrap the compliant schema into a versionable via the provider's adapter.

        A typed adapter that refuses a raw schema yields a meta node carrying the
        schema-derived ``fields`` instead, so the engine can still reconcile it.
        """
        adapter = self.provider.adapter
        try:
            return adapter.versionable(
                self.compliant(),  # ty: ignore[invalid-argument-type]
                kind=self.kind,
                version=self.version,
            )
        except (AttributeError, TypeError, ValueError):
            return VersionNode[Any, Any](
                _model=None,
                _value=adapter.of(self.version),
                _kind=self.kind,
                fields=self.fields(),
            )


class ComponentReflection(ABC):
    """One host primitive type: traverse its entities, emit nodes, materialize.

    :meth:`reflect` yields a node per versioned primitive; unversioned ones are
    skipped. :meth:`virtual` materializes a primitive for a registered version
    with no physical entity. Both are bound to one model adapter.
    """

    def __init__(
        self, adapter: ModelAdapter, *, detector: InjectionDetector | None = None
    ) -> None:
        self._adapter = adapter
        self._detector = detector

    @property
    def adapter(self) -> ModelAdapter:
        return self._adapter

    @abstractmethod
    def components(self, server: FastMCP) -> AsyncIterator[Any]:
        """Yield every physical entity of this provider's type from *server*."""

    async def reflect(self, server: FastMCP) -> AsyncIterator[ReflectedNode]:
        async for component in self.components(server):
            node = self.node(component)
            if node is not None:
                yield node

    def node(self, component: Any) -> ReflectedNode | None:
        """Normalize *component*, or ``None`` when it declares no version."""
        version = self.version(component)
        if version is None:
            return None
        return ReflectedNode(
            provider=self,
            kind=self.kind(component),
            version=version,
            schema=self.schema(component),
            injected=self.injected(component),
            handler=self.handler(component),
            policy=self.policy(component),
        )

    def policy(self, component: Any) -> Policy | None:
        """The convergence policy declared in the component's ``meta``, if any.

        Accepts a version string or a per-kind mapping (the JSON subset of a
        pyverge target policy); anything else is ignored.
        """
        meta = getattr(component, "meta", None)
        if not isinstance(meta, dict):
            return None
        declared = meta.get("policy")
        if isinstance(declared, str):
            return declared
        if isinstance(declared, dict) and all(
            isinstance(k, str) and isinstance(v, str) for k, v in declared.items()
        ):
            return declared
        return None

    def kind(self, component: Any) -> str:
        return str(component.name)

    def version(self, component: Any) -> str | None:
        version = getattr(component, "version", None)
        return None if version is None else str(version)

    def handler(self, component: Any) -> Callable[..., Any] | None:
        return getattr(component, "fn", None) or getattr(component, "run", None)

    def injected(self, component: Any) -> frozenset[str]:
        handler = self.handler(component)
        if handler is None:
            return frozenset()
        return frozenset(injected_names(handler, self._detector))

    @abstractmethod
    def schema(self, component: Any) -> dict[str, Any]:
        """Return the component's input schema document."""

    @abstractmethod
    def virtual(
        self, server: FastMCP, kind: str, version: str, schema: dict, fn: Callable
    ) -> Any:
        """Materialize a virtual ``kind@version`` primitive on *server*.

        The schema is the registered model's JSON schema (identity fields
        dropped); *fn* is the converging callable.
        """

    @staticmethod
    def schema_fields(schema: dict) -> list[str]:
        return list(schema.get("properties", {}))

    @staticmethod
    def signature(fn: Callable, names: list[str], *, required_first: bool) -> Callable:
        """Wrap *fn* so FastMCP's ``from_function`` sees one parameter per field.

        The converging callable is ``**kwargs``-only, but the FastMCP factories
        validate parameters against the signature. This exposes each schema
        field as a parameter (the first required when *required_first*, for a
        resource URI's path parameter).
        """

        def indirection(**kwargs):
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
                        default=inspect.Parameter.empty
                        if required_first and i == 0
                        else None,
                    )
                    for i, name in enumerate(names)
                ]
            ),
        )
        return indirection


class ToolReflection(ComponentReflection):
    """Reflect FastMCP tools (each tool's ``parameters`` schema)."""

    async def components(self, server: FastMCP) -> AsyncIterator[Any]:
        for tool in await server.list_tools():
            yield tool

    def schema(self, component: Any) -> dict[str, Any]:
        return dict(component.parameters)

    def virtual(
        self, server: FastMCP, kind: str, version: str, schema: dict, fn: Callable
    ) -> Any:
        return server.add_tool(
            FunctionTool(name=kind, version=version, parameters=schema, fn=fn)
        )


class PromptReflection(ComponentReflection):
    """Reflect FastMCP prompts (arguments synthesized into an object schema)."""

    async def components(self, server: FastMCP) -> AsyncIterator[Any]:
        for prompt in await server.list_prompts():
            yield prompt

    def schema(self, component: Any) -> dict[str, Any]:
        props: dict[str, Any] = {}
        required: list[str] = []
        for arg in component.arguments or []:
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

    def virtual(
        self, server: FastMCP, kind: str, version: str, schema: dict, fn: Callable
    ) -> Any:
        names = self.schema_fields(schema)
        prompt = FunctionPrompt.from_function(
            self.signature(fn, names, required_first=False), name=kind, version=version
        )
        # The factory derives arguments from ``fn``'s signature; the registered
        # model's schema is the contract, so it replaces them.
        prompt.arguments = [
            PromptArgument(
                name=name,
                description=prop.get("description"),
                required=name in schema.get("required", []),
            )
            for name, prop in schema.get("properties", {}).items()
        ]
        return server.add_prompt(prompt)


class ResourceReflection(ComponentReflection):
    """Reflect FastMCP resources and templates (their ``parameters`` schema).

    *uri_scheme* prefixes a virtual resource's URI template, so virtual
    templates match the physical ones.
    """

    def __init__(
        self,
        adapter: ModelAdapter,
        *,
        detector: InjectionDetector | None = None,
        uri_scheme: str = "",
    ) -> None:
        super().__init__(adapter, detector=detector)
        self._uri_scheme = uri_scheme

    async def components(self, server: FastMCP) -> AsyncIterator[Any]:
        for resource in await server.list_resources():
            yield resource
        for template in await server.list_resource_templates():
            yield template

    def schema(self, component: Any) -> dict[str, Any]:
        parameters = getattr(component, "parameters", None)
        return dict(parameters) if parameters else {"type": "object"}

    def kind(self, component: Any) -> str:
        name = component.name
        if name:
            return str(name)
        return str(self.uri_template(component))

    def uri_template(self, component: Any) -> str | None:
        return getattr(component, "uri_template", None) or getattr(
            component, "uri", None
        )

    def uri_template_for(self, kind: str, schema: dict) -> str:
        """URI template a virtual resource for *schema* exposes.

        The first property is the path parameter, the rest optional query
        parameters. Without a scheme, the kind namespaces the path.
        """
        names = self.schema_fields(schema)
        if not names:
            raise ValueError(f"kind {kind!r} has no properties for a URI template")
        prefix = self._uri_scheme or f"{kind}/"
        template = f"{prefix}{{{names[0]}}}"
        rest = names[1:]
        if rest:
            template += "{?" + ",".join(rest) + "}"
        return template

    def virtual(
        self, server: FastMCP, kind: str, version: str, schema: dict, fn: Callable
    ) -> Any:
        names = self.schema_fields(schema)
        template = FunctionResourceTemplate.from_function(
            self.signature(fn, names, required_first=True),
            uri_template=self.uri_template_for(kind, schema),
            name=kind,
            version=version,
        )
        # The factory derives parameters from ``fn``'s signature; the registered
        # model's schema is the contract, so it replaces them.
        template.parameters = schema
        return server.add_template(template)


__all__ = [
    "ComponentReflection",
    "PromptReflection",
    "ReflectedNode",
    "ResourceReflection",
    "ToolReflection",
]
