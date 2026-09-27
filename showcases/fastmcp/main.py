"""FastMCP integration showcase — lifecycle hook + middleware.

A versioned FastMCP server backed by the pyverge engine. The **physical tool
is its own anchor**: :class:`~pyverge.adapters.fastmcp.ToolRegistry` —
a standard FastMCP ``lifespan`` hook — reflects the server through
``list_tools`` and materializes every physical versioned tool's signature into
its manager (the tool's ``weather.json``). The customer registers migrations
**after** the anchors exist, so the engine can reconstruct the older endpoint
from the anchor. The registry then precomputes migration paths and
materializes virtual tools for the remaining versions. A
:class:`ConvergeMiddleware` converges each call's arguments — nested versioned
models included — to the policy target before the handler runs — fast, because
the path is precomputed, not rebuilt per call.

The per-tool policy lives on the **registry**, not on the tool definition. A
kind is versioned only when a policy is recorded for it; the fallback is
disabled by default, so a tool that must stay plain simply declares no policy.

This directory is self-contained, not a package: a plain script plus the
``migrations/`` spec it loads.  Run from the repo root (pyverge installed)::

    uv run python -m showcases.fastmcp.main

or directly::

    .venv/bin/python main.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import semver
from fastmcp import FastMCP

from pyverge import Manager
from pyverge.adapters.fastmcp import ConvergeMiddleware, ToolRegistry
from pyverge.migration import (
    JsonPatchMigration,
    JsonSchemaModelAdapter,
    MigrationSettings,
)

ROOT = Path(__file__).resolve().parent

ToolManager = Manager[semver.Version].configure(
    MigrationSettings(
        direction="forward",
        on_missing_path="raise",
        on_missing="reconstruct_model",
    ),
    JsonSchemaModelAdapter(version_property="version", kind_property="kind"),
)

manager = ToolManager()

reflection = ToolRegistry(
    manager,
    policies={"search_weather": "latest"},
    fallback_policy=None,
)

mcp = FastMCP(
    "WeatherServer",
    middleware=[ConvergeMiddleware(reflection)],
    lifespan=reflection,
)


@mcp.tool(version="2.0.0")
def search_weather(city: str, units: str = "celsius", humidity: bool = False) -> dict:
    """Search weather for a city (target: v2).

    A call against the v1 schema (via the virtual tool) converges to this v2
    shape before the handler runs.
    """
    return {"city": city, "units": units, "humidity": humidity}


async def _prepare() -> None:
    """Materialize the physical anchors, then register the migration.

    The physical tool *is* the v2 anchor — its signature is reflected into a
    model.  Only then can the engine reconstruct v1 from that anchor when the
    migration is registered.
    """
    await reflection.search(mcp)
    await reflection.register(mcp)
    manager.store_migration(
        ("search_weather", "1.0.0", "2.0.0"),
        JsonPatchMigration(
            json.load((ROOT / "migrations/weather_100_200.json").open())
        ).patch,
    )


asyncio.run(_prepare())

if __name__ == "__main__":
    mcp.run()
