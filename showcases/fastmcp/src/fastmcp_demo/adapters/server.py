"""FastMCP server adapter.

Builds the ``FastMCP`` server, the ``ToolRegistry`` lifespan hook and the
``ConvergeMiddleware``, wiring them to the domain manager. This is the only
module that imports FastMCP.
"""

from __future__ import annotations

from typing import Any

from fastmcp import FastMCP

from pyverge.adapters.fastmcp import ConvergeMiddleware, ToolRegistry

from ..settings import GraphSettings


def build_registry(manager: Any, graph: GraphSettings) -> ToolRegistry:
    """Return the lifespan hook routing the kind to *manager*."""
    return ToolRegistry(
        manager,
        policies={graph.kind: graph.policy},
        fallback_policy=None,
    )


def build_server(registry: ToolRegistry, graph: GraphSettings) -> FastMCP:
    """Return a FastMCP server exposing the physical anchor (the newest version).

    The physical tool *is* its own anchor: its signature is reflected into the
    newest model. Older versions are served by virtual tools materialized
    during the ``enrich`` phase.
    """
    mcp = FastMCP(
        "WeatherServer",
        middleware=[ConvergeMiddleware(registry)],
        lifespan=registry,
    )

    @mcp.tool(version="3.0.0")
    def search_weather(
        city: str,
        units: str = "celsius",
        humidity: bool = False,
        wind: float = 0.0,
    ) -> dict:
        """Search weather for a city (target: v3).

        A call against an older schema (via a virtual tool) converges to this
        v3 shape before the handler runs.
        """
        return {
            "city": city,
            "units": units,
            "humidity": humidity,
            "wind": wind,
        }

    return mcp
