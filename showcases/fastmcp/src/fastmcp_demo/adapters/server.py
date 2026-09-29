"""FastMCP server adapter.

Builds the ``FastMCP`` server, wiring the physical primitives (tool, prompt,
resource) in :mod:`fastmcp_demo.adapters.tools` to the domain manager. This is
the only module that imports FastMCP.

The discovery lifecycle is wired as the server's **lifespan** — the user's
concern, per FastMCP's model. :func:`build_lifespan` runs the tool discovery's
phases once at startup; FastMCP enters it whenever the server is run through a
transport or client.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastmcp import FastMCP
from fastmcp.exceptions import NotFoundError
from fastmcp.server.context import Context
from fastmcp.server.transforms import GetToolNext, Transform
from fastmcp.server.transforms.search import BM25SearchTransform
from fastmcp.tools.base import Tool, ToolResult
from fastmcp.utilities.versions import VersionSpec

from pyverge.adapters.fastmcp import (
    PromptReflection,
    ResourceReflection,
    ToolDiscovery,
    ToolReflection,
)
from pyverge.types import Attachable

from ..settings import GraphSettings, ServerSettings
from .tools import search_weather, weather_briefing, weather_reading

logger = logging.getLogger(__name__)


class VersionAliasTransform(Transform):
    """Expose every version of a versioned tool under its own callable name.

    FastMCP routes a versioned call natively through ``version=`` /
    ``_meta.fastmcp.version``. A raw-MCP client — or a proxy that cannot set
    request metadata — can only address a tool by name, so it can reach the
    latest version alone. This transform surfaces each registered version as a
    distinct name ``"<tool>.v<version>"`` carrying that version's own schema, so
    any client can call a specific version by name. The bare name keeps serving
    the latest version.
    """

    separator = ".v"

    async def list_tools(self, tools: Sequence[Tool]) -> Sequence[Tool]:
        expanded: list[Tool] = []
        for tool in tools:
            expanded.append(tool)
            if tool.version is None:
                continue
            alias = f"{tool.name}{self.separator}{tool.version}"
            expanded.append(
                tool.model_copy(
                    update={
                        "name": alias,
                        "description": (
                            f"{tool.description or ''}\n\n(version {tool.version})"
                        ).strip(),
                    }
                )
            )
        return expanded

    async def get_tool(
        self, name: str, call_next: GetToolNext, *, version: VersionSpec | None = None
    ) -> Tool | None:
        base, separator, pinned = name.rpartition(self.separator)
        if separator and base and pinned:
            return await call_next(base, version=VersionSpec(eq=pinned))
        return await call_next(name, version=version)


class VersionedSearchTransform(BM25SearchTransform):
    """BM25 search whose ``call_tool`` proxy accepts a version.

    The stock proxy calls ``ctx.fastmcp.call_tool(name, arguments)``, which
    always serves the highest version — a versioned tool is reachable only via
    FastMCP's native ``version=``, which a raw-MCP proxy has no way to express.
    This subclass adds an optional ``version`` argument that routes through the
    same native negotiation, so a caller can exercise any registered version.
    """

    def _make_call_tool(self) -> Tool:
        transform = self

        async def call_tool(
            name: Annotated[str, "The name of the tool to call"],
            arguments: Annotated[
                dict[str, Any] | None, "Arguments to pass to the tool"
            ] = None,
            version: Annotated[
                str | None,
                "Tool version to call (e.g. '1.0.0'); omit for the latest",
            ] = None,
            ctx: Context = None,  # type: ignore[assignment]  # ty:ignore[invalid-parameter-default]
        ) -> ToolResult:
            """Call a tool by name, optionally at a specific version.

            Use this to execute tools discovered via search_tools. When
            ``version`` is omitted the highest registered version is served.
            """
            if name in {transform._call_tool_name, transform._search_tool_name}:
                raise ValueError(
                    f"'{name}' is a synthetic search tool and cannot be called "
                    "via the call_tool proxy"
                )
            if not any(
                tool.name == name for tool in await transform.get_tool_catalog(ctx)
            ):
                raise NotFoundError(f"Unknown tool: {name!r}")
            spec = VersionSpec(eq=version) if version is not None else None
            return await ctx.fastmcp.call_tool(name, arguments, version=spec)

        return Tool.from_function(fn=call_tool, name=self._call_tool_name)


def build_discovery(
    manager: Any,
    graph: GraphSettings,
    *,
    hooks: Sequence[Attachable] = (),
) -> ToolDiscovery:
    """Return the discovery owning *manager*'s kinds.

    One manager per source: the discovery binds exactly one bounded context and
    one reflection provider per primitive type. ``hooks`` are attached to every
    migration edge, so each step is observable.
    """
    adapter = manager.adapter
    return ToolDiscovery(
        manager,
        providers=[
            ToolReflection(adapter),
            PromptReflection(adapter),
            ResourceReflection(adapter, uri_scheme="weather://"),
        ],
        policies=graph.policies,
        hooks=hooks,
    )


def build_search_transform(settings: ServerSettings) -> list[Any]:
    """Return the server transforms, or an empty list when search is disabled.

    The BM25 transform replaces the tool listing with a ``search_tools`` meta
    tool plus a ``call_tool`` proxy, so a client discovers tools on demand.
    Attached after the discovery lifecycle (see :func:`build_lifespan`).
    """
    if not settings.search_enabled:
        return [VersionAliasTransform()]
    return [
        VersionAliasTransform(),
        VersionedSearchTransform(
            max_results=settings.search_max_results,
            search_tool_name=settings.search_tool_name,
        ),
    ]


def build_lifespan(discovery: ToolDiscovery, *, transforms: Sequence[Any] = ()):
    """Return the server lifespan that drives the discovery lifecycle.

    The user owns the ordering: ``search`` -> ``register`` -> ``enrich``, once at
    startup. Re-running would re-materialize the virtual primitives.

    ``transforms`` are attached only *after* ``enrich``: a search transform
    replaces ``list_tools`` output with its synthetic surface, which would
    starve the discovery's ``search`` phase if attached first.
    """

    @asynccontextmanager
    async def app_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        logger.info("discovery lifecycle: search -> register -> enrich")
        await discovery.search(server)
        discovery.register()
        await discovery.enrich(server)
        for transform in transforms:
            server.add_transform(transform)
        logger.info("discovery lifecycle complete")
        yield {"discovery": discovery}

    return app_lifespan


def build_server(
    tool: Any = search_weather,
    *,
    lifespan: Any = None,
    middleware: Sequence[Any] = (),
) -> FastMCP:
    """Return a FastMCP server exposing one physical anchor per kind.

    Each decorated primitive *is* its kind's anchor; older versions are served by
    virtual primitives materialized during ``enrich``. ``lifespan`` drives the
    discovery lifecycle; ``middleware`` are host-supplied observers (e.g.
    tracing).
    """
    server = FastMCP(
        "WeatherServer",
        lifespan=lifespan,
        middleware=[*middleware],
        tools=[tool],
    )
    server.add_prompt(weather_briefing)
    server.add_template(weather_reading)
    return server
