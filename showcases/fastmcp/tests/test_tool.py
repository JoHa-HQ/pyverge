"""End-to-end tool behaviour, through the public client only.

Every case drives the ready FastMCP ``Client`` — the ``client`` fixture hands
over the session opened by the ``application`` fixture, so the server lifespan
(the discovery lifecycle) is active. A call at any registered version is
negotiated natively (``version=``), routed to the materialized virtual
primitive, and converges to the anchor handler.

The Hypothesis suite drives the same live client, swapping the mutable weather
fake's reading per example. The pinned reading is parametrized in, so the anchor
shape is snapshotted for a readable record.
"""

from __future__ import annotations

import pytest
from conftest import SNAPSHOT_READING, weather_reading
from fastmcp.exceptions import ToolError
from fastmcp_demo.domain import ALL_VERSIONS
from hypothesis import HealthCheck, given
from hypothesis import settings as hypothesis_settings
from syrupy.assertion import SnapshotAssertion

KIND = "search_weather"

#: Coordinates handed in explicitly — the handler must not geocode them away.
EXPLICIT_LATITUDE = 40.0
EXPLICIT_LONGITUDE = -3.0


class TestToolConvergence:
    @pytest.mark.parametrize("reading", [SNAPSHOT_READING], indirect=True)
    @pytest.mark.parametrize("version", ALL_VERSIONS, ids=ALL_VERSIONS)
    async def test_call_at_any_version_returns_anchor_shape(
        self, client, version: str, snapshot: SnapshotAssertion
    ) -> None:
        result = await client.call_tool(KIND, {"city": "Berlin"}, version=version)
        assert result.structured_content == snapshot

    @pytest.mark.parametrize("reading", [SNAPSHOT_READING], indirect=True)
    async def test_call_without_version_defaults_to_anchor(self, client) -> None:
        result = await client.call_tool(KIND, {"city": "Berlin"})
        assert result.structured_content is not None
        assert result.structured_content["temperature"] == SNAPSHOT_READING.temperature

    async def test_units_are_forwarded(self, client) -> None:
        result = await client.call_tool(
            KIND, {"city": "Berlin", "units": "fahrenheit"}, version="1.0.0"
        )
        assert result.structured_content is not None
        assert result.structured_content["units"] == "fahrenheit"

    async def test_explicit_coordinates_bypass_geocode(self, client) -> None:
        result = await client.call_tool(
            KIND,
            {
                "city": "anywhere",
                "coordinates": {
                    "kind": "coordinates",
                    "version": "1.0.0",
                    "latitude": EXPLICIT_LATITUDE,
                    "longitude": EXPLICIT_LONGITUDE,
                },
            },
        )
        assert result.structured_content is not None
        coordinates = result.structured_content["coordinates"]
        assert coordinates["latitude"] == EXPLICIT_LATITUDE
        assert coordinates["longitude"] == EXPLICIT_LONGITUDE

    async def test_unknown_city_surfaces_an_error(self, client) -> None:
        with pytest.raises(ToolError):
            await client.call_tool(KIND, {"city": "nowhere"})


class TestSearchProxy:
    """The ``call_tool`` proxy from the search transform routes versions."""

    @pytest.mark.parametrize("reading", [SNAPSHOT_READING], indirect=True)
    @pytest.mark.parametrize("version", ALL_VERSIONS, ids=ALL_VERSIONS)
    async def test_proxy_forwards_version(
        self, client, version: str, snapshot: SnapshotAssertion
    ) -> None:
        result = await client.call_tool(
            "call_tool",
            {"name": KIND, "arguments": {"city": "Berlin"}, "version": version},
        )
        assert result.structured_content == snapshot

    @pytest.mark.parametrize("reading", [SNAPSHOT_READING], indirect=True)
    async def test_proxy_without_version_defaults_to_anchor(self, client) -> None:
        result = await client.call_tool(
            "call_tool", {"name": KIND, "arguments": {"city": "Berlin"}}
        )
        assert result.structured_content is not None
        assert result.structured_content["temperature"] == SNAPSHOT_READING.temperature


class TestVersionAliases:
    """Every version is callable by its own name, for name-only clients."""

    @pytest.mark.parametrize("reading", [SNAPSHOT_READING], indirect=True)
    @pytest.mark.parametrize("version", ALL_VERSIONS, ids=ALL_VERSIONS)
    async def test_alias_call_converges_to_anchor(
        self, client, version: str, snapshot: SnapshotAssertion
    ) -> None:
        result = await client.call_tool(f"{KIND}.v{version}", {"city": "Berlin"})
        assert result.structured_content == snapshot

    async def test_alias_is_searchable(self, client) -> None:
        result = await client.call_tool("search_tools", {"query": "weather"})
        names = {
            hit["name"] for hit in (result.structured_content or {}).get("result", [])
        }
        for version in ALL_VERSIONS:
            assert f"{KIND}.v{version}" in names


class TestArbitraryReadings:
    @given(reading=weather_reading)
    @hypothesis_settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
    async def test_any_reading_converges_to_the_anchor_shape(
        self, reading, application, client
    ) -> None:
        application.weather.reading = reading
        expected = {
            "city": "Berlin",
            "units": "celsius",
            "temperature": reading.temperature,
            "humidity": reading.humidity,
            "wind": reading.wind,
            "coordinates": {
                "kind": "coordinates",
                "version": "1.0.0",
                "latitude": 52.52,
                "longitude": 13.405,
            },
        }
        for version in ALL_VERSIONS:
            result = await client.call_tool(KIND, {"city": "Berlin"}, version=version)
            assert result.structured_content == expected
