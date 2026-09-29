from __future__ import annotations

import inspect
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from fastmcp.prompts.base import PromptArgument
from fastmcp.prompts.function_prompt import FunctionPrompt
from fastmcp.resources.template import FunctionResourceTemplate
from fastmcp.tools.function_tool import FunctionTool

from pyverge.core import VersionNode
from pyverge.types import ModelAdapter, Versionable

from .injection import InjectionDetector, injected_names

if TYPE_CHECKING:
    from fastmcp import FastMCP


@dataclass(frozen=True)
class ReflectedNode:
    """A versioned physical entity, normalized for the version graph.

    Emitted by a provider's :meth:`ComponentReflection.reflect`. Discovery
    consumes nodes only — it never reads a FastMCP primitive's internals. The
    node is also the schema→versionable bridge: :meth:`versionable` drops the
    injected (wired) parameters, injects the identity fields under the
    adapter's configured property names, and wraps the result through the
    provider's adapter.
    """

    provider: ComponentReflection
    kind: str
    version: str
    schema: dict[str, Any]
    injected: frozenset[str]
    handler: Callable[..., Any] | None

    def _identity(self) -> tuple[str, str]:
        """Return the ``(kind_property, version_property)`` field names."""
        adapter = self.provider.adapter
        return adapter.kind_property, adapter.version_property

    def compliant(self) -> dict[str, Any]:
        """Return the schema with injected params dropped and identity injected."""
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
        """Return the reflected payload fields, minus the identity fields."""
        identity = set(self._identity())
        return frozenset(set(self.compliant().get("properties", {})) - identity)

    def versionable(self) -> Versionable:
        """Wrap the compliant schema into a node via the provider's adapter.

        A schema-based adapter materializes the document into a model; a typed
        adapter that refuses a raw schema yields a meta node carrying the
        schema-derived ``fields`` instead, so the engine can still reconcile it
        against the model the host registered.
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
    """Factory for one host primitive type: traverse, emit nodes, materialize.

    One provider per primitive type — a tool, a prompt or a resource — bridging
    the host's primitive type and pyverge's version graph. It traverses the
    server's physical entities of its type (its *tree*) and emits one
    :class:`ReflectedNode` per entity **marked for versioning**; the unmarked
    ones are invisible to discovery, so discovery stays free of any FastMCP
    object shape and consumes nodes, never primitives.

    The provider is bound once with the manager's model adapter (for
    schema→versionable work) and an optional injection detector. Kind and
    version come from the entity itself. :meth:`reflect` yields only physical
    nodes: a virtual component is synthesized from the registered graph, so
    returning it here would make discovery unable to tell a host-declared
    entity from one it already materialized. :meth:`virtual` materializes that
    synthesized primitive for a registered version with no physical entity.
    """

    def __init__(
        self, adapter: ModelAdapter, *, detector: InjectionDetector | None = None
    ) -> None:
        self._adapter = adapter
        self._detector = detector

    @property
    def adapter(self) -> ModelAdapter:
        """The bound model adapter."""
        return self._adapter

    # -- traversal ----------------------------------------------------------

    @abstractmethod
    def components(self, server: FastMCP) -> AsyncIterator[Any]:
        """Yield every physical entity of this provider's type from *server*."""

    async def reflect(self, server: FastMCP) -> AsyncIterator[ReflectedNode]:
        """Emit a node per physical entity marked for versioning.

        An entity is marked when it declares a version. Unmarked entities are
        skipped — they belong to no version graph.
        """
        async for component in self.components(server):
            node = self.node(component)
            if node is not None:
                yield node

    def node(self, component: Any) -> ReflectedNode | None:
        """Normalize *component*, or ``None`` when it is not marked for versioning."""
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
        )

    # -- primitive reading --------------------------------------------------

    def kind(self, component: Any) -> str:
        """Return the entity's kind (its identity key)."""
        return str(component.name)

    def version(self, component: Any) -> str | None:
        """Return the entity's version, or ``None`` when it is not marked."""
        version = getattr(component, "version", None)
        return None if version is None else str(version)

    def handler(self, component: Any) -> Callable[..., Any] | None:
        """Return the callable behind *component*, or ``None`` if it has none."""
        return getattr(component, "fn", None) or getattr(component, "run", None)

    def injected(self, component: Any) -> frozenset[str]:
        """Return the names of the component's injected (wired) parameters."""
        handler = self.handler(component)
        if handler is None:
            return frozenset()
        return frozenset(injected_names(handler, self._detector))

    @abstractmethod
    def schema(self, component: Any) -> dict[str, Any]:
        """Return the component's input schema document."""

    # -- factory ------------------------------------------------------------

    @abstractmethod
    def virtual(
        self, server: FastMCP, kind: str, version: str, schema: dict, fn: Callable
    ) -> Any:
        """Materialize a virtual *kind*@*version* primitive on *server*.

        The schema is the registered model's JSON schema (identity fields
        already dropped); *fn* is the converging indirection.
        """

    # -- helpers ------------------------------------------------------------

    @staticmethod
    def schema_fields(schema: dict) -> list[str]:
        """Return the field names of a JSON schema document."""
        return list(schema.get("properties", {}))

    @staticmethod
    def signature(fn: Callable, names: list[str], *, required_first: bool) -> Callable:
        """Wrap *fn* so FastMCP's ``from_function`` sees one parameter per field.

        The converging indirection is ``**kwargs``-only, but the FastMCP
        factories validate the component's parameters against the callable's
        signature. This exposes each schema field as a parameter (the first one
        required when *required_first*, for a resource URI's path parameter)
        and forwards everything.
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
        # The factory derives the arguments from ``fn``'s signature; the
        # registered model's schema is the contract, so it replaces them.
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

    *uri_scheme* is the prefix a virtual resource's URI template uses (e.g.
    ``"weather://"``), so virtual templates match the physical ones.
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
        """Return the URI template a virtual resource for *schema* exposes.

        The template mirrors the physical shape: *uri_scheme* is the prefix
        (e.g. ``"weather://"``), the first property is the path parameter (a
        template needs at least one), the rest are optional query parameters.
        Without a scheme, the kind namespaces the path.
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
        # The factory derives the schema from ``fn``'s signature (the URI
        # parameters); the registered model's schema is the contract, so it
        # replaces the derived one.
        template.parameters = schema
        return server.add_template(template)


__all__ = [
    "ComponentReflection",
    "PromptReflection",
    "ReflectedNode",
    "ResourceReflection",
    "ToolReflection",
]
