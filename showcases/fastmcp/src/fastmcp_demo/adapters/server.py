"""FastMCP server adapter.

Builds the ``FastMCP`` server and the ``ToolRegistry`` lifespan hook, wiring
them to the domain manager. The physical tool lives in
:mod:`fastmcp_demo.adapters.tools`; this module only assembles the server around
it. This is the only module that imports FastMCP.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP

from pyverge.adapters.fastmcp import ConvergeMiddleware, ToolRegistry

from ..domain import ANCHOR_VERSION
from ..settings import GraphSettings
from .tools import search_weather


def build_registry(manager: Any, graph: GraphSettings) -> ToolRegistry:
    """Return the lifespan hook routing the kind to *manager*."""
    return ToolRegistry(
        manager,
        policies={graph.kind: graph.policy},
        fallback_policy=None,
    )


def build_server(
    registry: ToolRegistry,
    graph: GraphSettings,
    tool: Callable[..., Any] = search_weather,
) -> FastMCP:
    """Return a FastMCP server exposing the physical anchor (the newest version).

    The physical tool *is* its own anchor: its signature (with injected
    parameters hidden) is reflected into the newest model. Older versions are
    served by virtual tools materialized during the ``enrich`` phase.
    """
    mcp = FastMCP(
        "WeatherServer",
        middleware=[ConvergeMiddleware(registry)],
        lifespan=registry,
    )
    mcp.tool(tool, version=ANCHOR_VERSION)
    return mcp
