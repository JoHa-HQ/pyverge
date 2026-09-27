"""FastMCP server adapter.

Builds the ``FastMCP`` server and the ``ToolRegistry`` lifespan hook, wiring
them to the domain manager. The physical tool lives in
:mod:`fastmcp_demo.adapters.tools`; this module only assembles the server around
it. This is the only module that imports FastMCP.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from fastmcp import FastMCP

from pyverge.adapters.fastmcp import (
    ConvergeMiddleware,
    ToolRegistry,
    make_tool,
)
from pyverge.types import Attachable

from ..domain import ANCHOR_VERSION
from ..settings import GraphSettings
from .tools import search_weather


def build_registry(
    manager: Any,
    graph: GraphSettings,
    *,
    hooks: Sequence[Attachable] = (),
) -> ToolRegistry:
    """Return the lifespan hook owning *manager*'s kind.

    One manager per source: the registry binds exactly one bounded context.
    ``hooks`` are attached to every migration edge, so each step is observable.
    """
    return ToolRegistry(
        manager,
        policies={graph.kind: graph.policy},
        fallback_policy=None,
        hooks=hooks,
    )


def build_server(
    registry: ToolRegistry,
    graph: GraphSettings,
    tool: Callable[..., Any] = search_weather,
    *,
    span_factory=None,
) -> FastMCP:
    """Return a FastMCP server exposing the physical anchor (the newest version).

    The physical tool *is* its own anchor: its signature (with injected
    parameters hidden) is reflected into the newest model. Older versions are
    served by virtual tools materialized during the ``enrich`` phase.
    ``span_factory`` opens a parent span per call for the tracing middleware.
    """
    mcp = FastMCP(
        "WeatherServer",
        middleware=[ConvergeMiddleware(registry, span_factory=span_factory)],
        lifespan=registry,
    )
    mcp.add_tool(make_tool(tool, version=ANCHOR_VERSION))
    return mcp
