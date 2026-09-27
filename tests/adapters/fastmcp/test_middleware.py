"""Suite: ConvergeMiddleware wiring against the reflection lifecycle hook.

Two call shapes are covered:
* a call carrying an explicit version → converged in-place, never passthrough,
* a call without a version → passed straight through.
"""

from __future__ import annotations

import asyncio

import pytest
from fastmcp import FastMCP
from mcp.types import CallToolRequestParams

from pyverge.adapters.fastmcp import ConvergeMiddleware


class _Ctx:
    method = "tools/call"

    def __init__(self, message):
        self.message = message

    def copy(self, message):
        self.message = message
        return self


def _weather_server(calls: list | None = None) -> FastMCP:
    mcp = FastMCP("S")

    @mcp.tool(version="2.0.0")
    def search_weather(city: str, humidity: bool = False) -> dict:
        if calls is not None:
            calls.append((city, humidity))
        return {"city": city, "humidity": humidity}

    return mcp


def _configured(weather_chain, configured_server, mcp):
    return configured_server(weather_chain, mcp, policies={"search_weather": "latest"})


class TestConvergeMiddleware:
    @pytest.mark.parametrize(
        ("version", "meta"),
        [
            ("1.0.0", {"fastmcp": {"version": "1.0.0"}}),
            ("1.0.0", None),
        ],
        ids=["meta", "argument"],
    )
    def test_converges_versioned_call(
        self,
        weather_chain,
        configured_server,
        version: str,
        meta,
    ):
        mcp = _weather_server()
        _, registry = _configured(weather_chain, configured_server, mcp)
        middleware = ConvergeMiddleware(registry)

        async def call_next(ctx):
            raise AssertionError("converged call must not pass through")

        arguments = {"city": "Berlin"}
        if meta is None:
            arguments["version"] = version
        ctx = _Ctx(CallToolRequestParams(name="search_weather", arguments=arguments))
        if meta is not None:
            ctx.message.meta = meta
        result = asyncio.run(middleware.on_call_tool(ctx, call_next))  # ty: ignore[invalid-argument-type]
        assert result.structured_content == {"city": "Berlin", "humidity": False}

    def test_no_version_passes_through(self, weather_chain, configured_server):
        mcp = _weather_server()
        _, registry = _configured(weather_chain, configured_server, mcp)
        middleware = ConvergeMiddleware(registry)

        ctx = _Ctx(
            CallToolRequestParams(name="search_weather", arguments={"city": "x"})
        )
        assert ctx.message.meta is None

        async def call_next(ctx):
            return "passthrough"

        assert asyncio.run(middleware.on_call_tool(ctx, call_next))  # ty: ignore[invalid-argument-type] == "passthrough"
