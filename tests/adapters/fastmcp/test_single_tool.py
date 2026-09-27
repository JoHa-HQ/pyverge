"""Suite: one physical tool serves every registered version of its kind.

Pre-registered chain in the manager; a single ``@mcp.tool(version=...)``
declaration; the adapter reflects, registers, enriches and then serves calls
against *any* registered version of that kind via a precomputed path.
"""

from __future__ import annotations

import pytest
from fastmcp import FastMCP

from pyverge.migration import JsonSchemaModelAdapter


def _server(version: str, calls: list):
    mcp = FastMCP("S")

    @mcp.tool(version=version)
    def search_weather(city: str, humidity: bool = False) -> dict:
        calls.append((city, humidity))
        return {"city": city, "humidity": humidity}

    return mcp


class TestSinglePhysicalTool:
    @pytest.mark.parametrize(
        ("call_version", "expected_calls"),
        [
            ("1.0.0", [("Berlin", False)]),
            ("2.0.0", [("Berlin", False)]),
        ],
        ids=["virtual-version", "physical-version"],
    )
    def test_one_tool_serves_all_versions(
        self,
        weather_chain,
        configured_server,
        call_version: str,
        expected_calls: list,
    ):
        calls: list[tuple] = []
        mcp = _server("2.0.0", calls)

        _, registry = configured_server(
            weather_chain, mcp, policies={"search_weather": "latest"}
        )

        assert set(registry._physical) == {("search_weather", "2.0.0")}
        assert registry.path("search_weather", "1.0.0") == "2.0.0"

        handler = registry.delegate("search_weather", call_version)
        assert handler is not None
        result = handler(city="Berlin")
        assert result == {"city": "Berlin", "humidity": False}
        assert calls == expected_calls

    @pytest.mark.parametrize(
        ("version", "path_to"),
        [("2.0.0", "2.0.0"), ("1.0.0", "2.0.0")],
        ids=["direct", "converged"],
    )
    def test_delegate_targets_policy(
        self,
        weather_chain,
        configured_server,
        version: str,
        path_to: str,
    ):
        calls: list[tuple] = []
        mcp = _server("2.0.0", calls)

        _, registry = configured_server(
            weather_chain, mcp, policies={"search_weather": "latest"}
        )

        handler = registry.delegate("search_weather", version)
        assert handler is not None
        result = handler(city="Berlin")
        assert result["humidity"] is False
        assert calls == [("Berlin", False)]

    @pytest.mark.parametrize(
        ("policy", "path_to"),
        [("latest", "2.0.0"), ("earliest", "1.0.0")],
        ids=["latest", "earliest"],
    )
    def test_delegate_respects_policy(
        self,
        weather_chain,
        configured_server,
        policy: str,
        path_to: str,
    ):
        calls: list[tuple] = []
        mcp = FastMCP("S")

        @mcp.tool(version="2.0.0")
        def search_weather(city: str, humidity: bool = False) -> dict:
            calls.append((city, humidity))
            return {"city": city, "humidity": humidity}

        _, registry = configured_server(
            weather_chain, mcp, policies={"search_weather": policy}
        )
        assert registry.path("search_weather", "1.0.0") == path_to

    def test_delegate_none_when_kind_unowned(self, weather_chain, configured_server):
        mcp = FastMCP("S")

        @mcp.tool
        def unrelated(a: str) -> dict:
            return {"a": a}

        _, registry = configured_server(weather_chain, mcp)
        assert registry.delegate("unrelated", "1.0.0") is None

    def test_physical_tool_becomes_anchor(
        self,
        weather_chain,
        configured_server,
    ):
        """A physical versioned tool materializes its own anchor when missing.

        A tool's signature *is* its model: when ``(kind, version)`` is not yet
        registered, the adapter reflects the physical tool into a model and
        stores it as the anchor — the raw schema no longer needs a separate
        registration (the ``weather.json`` case).  A typed adapter whose
        reflection yields no model still raises.
        """
        mcp = FastMCP("S")

        @mcp.tool(version="3.0.0")
        def search_weather(city: str, humidity: bool = False) -> dict:
            return {"city": city, "humidity": humidity}

        if isinstance(weather_chain.engine.adapter, JsonSchemaModelAdapter):
            _, registry = configured_server(
                weather_chain,
                mcp,
                policies={"search_weather": "latest"},
            )
            assert ("search_weather", "3.0.0") in registry._physical
        else:
            with pytest.raises(ValueError, match="materialize"):
                configured_server(
                    weather_chain,
                    mcp,
                    policies={"search_weather": "latest"},
                )
