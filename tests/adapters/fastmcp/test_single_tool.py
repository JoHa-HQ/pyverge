"""End-to-end: one physical tool serves every registered version of its kind.

A chain is registered in the manager; a single ``@mcp.tool(version=...)``
declaration is reflected, reconciled and enriched; calls at *any* registered
version then converge to the policy target through the public
``server.call_tool`` surface.
"""

from __future__ import annotations

import pytest
from conftest import call_tool, running_server
from fastmcp import FastMCP

KIND = "search_weather"


def _server(calls: list | None = None) -> FastMCP:
    mcp = FastMCP("S")

    @mcp.tool(version="2.0.0")
    def search_weather(city: str, humidity: bool = False) -> dict:
        if calls is not None:
            calls.append((city, humidity))
        return {"city": city, "humidity": humidity}

    return mcp


class TestOneToolServesAllVersions:
    @pytest.mark.parametrize(
        "call_version",
        ["1.0.0", "2.0.0"],
        ids=["virtual-version", "physical-version"],
    )
    def test_call_at_any_version_converges_to_the_physical_handler(
        self, weather_manager, call_version: str
    ) -> None:
        calls: list[tuple] = []
        mcp = running_server(weather_manager, _server(calls), policies={KIND: "latest"})

        result = call_tool(mcp, KIND, {"city": "Berlin", "version": call_version})

        assert result.structured_content == {"city": "Berlin", "humidity": False}
        assert calls == [("Berlin", False)]

    def test_unrelated_tool_is_left_untouched(self, weather_manager) -> None:
        mcp = FastMCP("S")

        @mcp.tool
        def unrelated(a: str) -> dict:
            return {"a": a}

        running_server(weather_manager, mcp, policies={KIND: "latest"})
        result = call_tool(mcp, "unrelated", {"a": "x"})
        assert result.structured_content == {"a": "x"}
