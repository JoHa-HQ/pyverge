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

    async def test_unknown_city_surfaces_an_error(self, client) -> None:
        with pytest.raises(ToolError):
            await client.call_tool(KIND, {"city": "nowhere"})


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
        }
        for version in ALL_VERSIONS:
            result = await client.call_tool(KIND, {"city": "Berlin"}, version=version)
            assert result.structured_content == expected
