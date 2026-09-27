"""End-to-end tool behaviour, through public interfaces only.

Every case drives the ready FastMCP server (``server.call_tool``): a call at any
registered version converges to the anchor handler and returns the live shape.
No internal wiring is assembled by the tests.

A Hypothesis strategy draws arbitrary valid readings, so convergence is checked
across the input space. The pinned reading is snapshotted for a readable record
of the anchor shape.
"""

from __future__ import annotations

import pytest
from conftest import SNAPSHOT_READING, call_tool, running_app, weather_reading
from fastmcp.exceptions import ToolError
from fastmcp_demo.domain import ALL_VERSIONS
from hypothesis import given
from syrupy.assertion import SnapshotAssertion

KIND = "search_weather"


class TestToolConvergence:
    @pytest.mark.parametrize("version", ALL_VERSIONS, ids=ALL_VERSIONS)
    def test_call_at_any_version_returns_anchor_shape(
        self, server, version: str, snapshot: SnapshotAssertion
    ) -> None:
        result = call_tool(server, KIND, {"city": "Berlin", "version": version})
        assert result.structured_content == snapshot

    def test_call_without_version_defaults_to_anchor(self, server) -> None:
        result = call_tool(server, KIND, {"city": "Berlin"})
        assert result.structured_content is not None
        assert result.structured_content["temperature"] == SNAPSHOT_READING.temperature

    def test_units_are_forwarded(self, server) -> None:
        result = call_tool(
            server, KIND, {"city": "Berlin", "units": "fahrenheit", "version": "1.0.0"}
        )
        assert result.structured_content is not None
        assert result.structured_content["units"] == "fahrenheit"

    def test_unknown_city_surfaces_an_error(self, server) -> None:
        with pytest.raises(ToolError):
            call_tool(server, KIND, {"city": "nowhere"})


class TestArbitraryReadings:
    @given(reading=weather_reading)
    def test_any_reading_converges_to_the_anchor_shape(self, reading) -> None:
        with running_app(reading) as app:
            expected = {
                "city": "Berlin",
                "units": "celsius",
                "temperature": reading.temperature,
                "humidity": reading.humidity,
                "wind": reading.wind,
            }
            for version in ALL_VERSIONS:
                result = call_tool(
                    app.server, KIND, {"city": "Berlin", "version": version}
                )
                assert result.structured_content == expected
