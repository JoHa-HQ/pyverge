"""End-to-end: a tool whose arguments embed versioned models.

A plain tool (stable signature) carries an argument that is a versioned model.
The middleware converges every embedded entry to its chain's latest version
before the handler runs. A declared-but-unregistered nested kind fails the
reflection lifecycle.
"""

from __future__ import annotations

import asyncio

import pytest
import semver
from conftest import call_tool, serve
from fastmcp import FastMCP
from pydantic import create_model

from pyverge import Manager
from pyverge.adapters.fastmcp import ConvergeMiddleware, ToolRegistry
from pyverge.migration import MigrationSettings, PydanticModelAdapter
from tests.examples.pydantic.semver_nested import (
    AddressV1,
    AddressV2,
    migrate_address_100_200,
)


class TestEmbeddedModelConvergence:
    @pytest.mark.parametrize(
        "model_adapter, registry",
        [
            pytest.param(
                PydanticModelAdapter,
                [
                    semver.Version,
                    "nested_test",
                    [AddressV1, AddressV2],
                    [((AddressV1, AddressV2), migrate_address_100_200)],
                ],
                id="pydantic",
            ),
        ],
        indirect=["model_adapter", "registry"],
    )
    def test_embedded_model_converges_before_the_handler(
        self, manager: type, registry
    ) -> None:
        mcp = FastMCP("S")

        @mcp.tool
        def search(location: dict) -> dict:
            return {"location": location}

        serve(manager, mcp)
        result = call_tool(
            mcp,
            "search",
            {
                "location": {
                    "kind": "Address",
                    "version": "1.0.0",
                    "street": "S",
                    "city": "C",
                }
            },
        )

        assert result.structured_content == {
            "location": {
                "kind": "Address",
                "version": "2.0.0",
                "street": "S",
                "city": "C",
                "country": None,
                "postal_code": None,
            }
        }


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

        @mcp.tool(name="search_weather", version="2.0.0")
        def search_weather(location: dict) -> dict:
            return {"location": location}

        registry = ToolRegistry(manager, policies={"search_weather": "latest"})
        mcp.middleware = [*mcp.middleware, ConvergeMiddleware(registry)]

        with pytest.raises(ValueError, match="references unregistered"):
            asyncio.run(_lifecycle(registry, mcp))


async def _lifecycle(registry: ToolRegistry, mcp: FastMCP) -> None:
    async with registry(mcp):
        pass
