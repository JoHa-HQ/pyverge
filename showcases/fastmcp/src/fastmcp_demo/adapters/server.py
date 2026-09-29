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
from typing import Any

from fastmcp import FastMCP

from pyverge.adapters.fastmcp import (
    PromptReflection,
    ResourceReflection,
    ToolDiscovery,
    ToolReflection,
)
from pyverge.types import Attachable

from ..settings import GraphSettings
from .tools import search_weather, weather_briefing, weather_reading

logger = logging.getLogger(__name__)


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


def build_lifespan(discovery: ToolDiscovery):
    """Return the server lifespan that drives the discovery lifecycle.

    The user owns the ordering: ``search`` -> ``register`` -> ``enrich``, once at
    startup. Re-running would re-materialize the virtual primitives.
    """

    @asynccontextmanager
    async def app_lifespan(server: FastMCP) -> AsyncIterator[dict[str, Any]]:
        logger.info("discovery lifecycle: search -> register -> enrich")
        await discovery.search(server)
        discovery.register()
        await discovery.enrich(server)
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
