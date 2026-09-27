"""Suite: multiple managers (Django-style).

Each manager owns a distinct set of kinds; the reflection router routes a
tool kind to exactly one owning manager.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP


@pytest.fixture
def tickets_chain(manager, store_schema):
    store_schema(manager, "book", "1.0.0", {"seat": {"type": "string"}}, ["seat"])
    store_schema(manager, "book", "2.0.0", {"seat": {"type": "string"}}, ["seat"])
    return manager


class TestMultipleManagers:
    def test_routes_kinds_to_their_owner(
        self, weather_chain, tickets_chain, configured_server
    ):
        mcp = FastMCP("S")

        @mcp.tool(version="2.0.0")
        def search_weather(city: str, humidity: bool = False) -> dict:
            return {"city": city, "humidity": humidity}

        @mcp.tool(version="2.0.0")
        def book(seat: str) -> dict:
            return {"seat": seat}

        _, registry = configured_server(
            [weather_chain, tickets_chain],
            mcp,
            policies={"search_weather": "latest", "book": "latest"},
        )

        assert registry.path("search_weather", "1.0.0") == "2.0.0"
        assert registry.delegate("search_weather", "1.0.0") is not None
        assert registry.delegate("book", "2.0.0") is not None
