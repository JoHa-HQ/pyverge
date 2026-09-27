"""End-to-end tool behaviour, through public interfaces only.

Every case drives the ready FastMCP server (``server.call_tool``): a call at any
registered version converges to the anchor handler and returns the live shape.
No internal wiring is assembled by the tests.
"""

from __future__ import annotations

import pytest
from conftest import FAKE_READING
from fastmcp.exceptions import ToolError
from fastmcp_demo.domain import ALL_VERSIONS

KIND = "search_weather"

ANCHOR_SHAPE = {
    "city": "Berlin",
    "units": "celsius",
    "temperature": FAKE_READING.temperature,
    "humidity": FAKE_READING.humidity,
    "wind": FAKE_READING.wind,
}


class TestToolConvergence:
    @pytest.mark.parametrize("version", ALL_VERSIONS, ids=ALL_VERSIONS)
    async def test_call_at_any_version_returns_anchor_shape(
        self, server, version: str
    ) -> None:
        result = await server.call_tool(KIND, {"city": "Berlin", "version": version})
        assert result.structured_content == ANCHOR_SHAPE

    async def test_call_without_version_defaults_to_anchor(self, server) -> None:
        result = await server.call_tool(KIND, {"city": "Berlin"})
        # An unversioned call to the physical tool runs the anchor handler.
        assert result.structured_content is not None
        assert result.structured_content["temperature"] == FAKE_READING.temperature

    async def test_units_are_forwarded(self, server) -> None:
        result = await server.call_tool(
            KIND, {"city": "Berlin", "units": "fahrenheit", "version": "1.0.0"}
        )
        assert result.structured_content is not None
        assert result.structured_content["units"] == "fahrenheit"

    async def test_unknown_city_surfaces_an_error(self, server) -> None:
        with pytest.raises(ToolError):
            await server.call_tool(KIND, {"city": "nowhere"})
