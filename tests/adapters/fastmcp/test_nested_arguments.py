"""End-to-end: a tool whose arguments embed versioned models.

The tool itself is plain (stable schema); an argument carries an embedded model
that is versioned. The middleware converges every embedded entry to its chain's
latest version before the handler runs — without touching the tool's own
handler. A declared-but-unregistered nested kind fails at startup.
"""

from __future__ import annotations

import asyncio

import pytest
import semver
from conftest import call_tool, store_model
from fastmcp import FastMCP
from pydantic import create_model

from pyverge import Manager
from pyverge.adapters.fastmcp import ConvergeMiddleware, ToolRegistry
from pyverge.migration import JsonPatchMigration, MigrationSettings
from pyverge.types import ManagerMigrationKey


def _chain(manager: Manager, kind: str, field: str, default: str) -> None:
    store_model(manager, kind, "1.0.0", {"city": {"type": "string"}}, ["city"])
    store_model(
        manager,
        kind,
        "2.0.0",
        {"city": {"type": "string"}, field: {"type": "string", "default": default}},
        ["city"],
    )
    manager.store_migration(
        ManagerMigrationKey(kind, "1.0.0", "2.0.0"),
        JsonPatchMigration(
            {
                "from": "1.0.0",
                "to": "2.0.0",
                "ops": [{"op": "add", "path": f"/{field}", "value": default}],
            }
        ).patch,
    )


class TestEmbeddedModelConvergence:
    def test_embedded_model_converges_before_the_handler(self, manager) -> None:
        _chain(manager, "location", "country", "DE")

        mcp = FastMCP("S")
        seen: list[dict] = []

        @mcp.tool
        def search_weather(location: dict) -> dict:
            seen.append(location)
            return {"location": location}

        registry = ToolRegistry(manager)
        mcp.middleware = [*mcp.middleware, ConvergeMiddleware(registry)]

        result = call_tool(
            mcp,
            "search_weather",
            {"location": {"kind": "location", "version": "1.0.0", "city": "Berlin"}},
        )

        assert result.structured_content == {
            "location": {
                "kind": "location",
                "version": "2.0.0",
                "city": "Berlin",
                "country": "DE",
            }
        }
        assert seen[0]["version"] == "2.0.0"


class TestUnregisteredReference:
    def test_unregistered_nested_kind_fails_at_startup(
        self, pydantic_model_adapter
    ) -> None:
        """A tool whose registered model references an unregistered kind fails.

        The reference walk sees every declared version; an absent one is a
        latent bug (the walker skips unregistered kinds), so the adapter fails
        the reflection lifecycle instead of silently serving stale children.
        """
        manager = Manager[semver.Version].configure(
            MigrationSettings(on_missing="reconstruct_model"), pydantic_model_adapter
        )()
        location = create_model(
            "Location", kind=(str, "location"), version=(str, "1.0.0"), city=(str, ...)
        )
        search_weather = create_model(
            "SearchWeather",
            kind=(str, "search_weather"),
            version=(str, "2.0.0"),
            location=(location, ...),
        )
        manager.store_model(search_weather)  # 'location' intentionally absent

        mcp = FastMCP("S")

        @mcp.tool(version="2.0.0")
        def search_weather(location: dict) -> dict:
            return {"location": location}

        registry = ToolRegistry(manager, policies={"search_weather": "latest"})
        with pytest.raises(ValueError, match="references unregistered"):
            asyncio.run(_lifecycle(registry, mcp))


async def _lifecycle(registry: ToolRegistry, mcp: FastMCP) -> None:
    async with registry(mcp):
        pass
