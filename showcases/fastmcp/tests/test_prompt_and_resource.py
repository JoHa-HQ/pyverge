"""End-to-end prompt and resource behaviour, through the public client only.

Each case drives the ready FastMCP ``Client`` — the async ``client`` fixture
opens a session so the server lifespan (the discovery lifecycle) is active. A
call at any registered version converges to the anchor handler, exactly like a
tool call. Older-version primitives are materialized during the discovery
``enrich`` phase and served by FastMCP's native version routing.
"""

from __future__ import annotations

import pytest
from conftest import SNAPSHOT_READING
from fastmcp_demo.domain import V1, V2

BRIEFING = "weather_briefing"
READING = "weather_reading"


class TestPromptConvergence:
    @pytest.mark.parametrize("version", [None, V1, V2])
    async def test_prompt_at_any_version_converges(self, client, version) -> None:
        result = await client.get_prompt(BRIEFING, {"city": "Berlin"}, version=version)
        text = result.messages[0].content.text
        assert text == f"Berlin: {SNAPSHOT_READING.temperature:.1f}°"

    async def test_prompt_style_is_forwarded(self, client) -> None:
        result = await client.get_prompt(
            BRIEFING, {"city": "Berlin", "style": "detailed"}
        )
        text = result.messages[0].content.text
        assert "humidity" in text and "wind" in text


class TestResourceConvergence:
    @pytest.mark.parametrize("version", [None, V1, V2])
    async def test_resource_at_any_version_converges(self, client, version) -> None:
        contents = await client.read_resource("weather://Berlin", version=version)
        assert contents[0].text == (
            f"Berlin: {SNAPSHOT_READING.temperature:.1f}° (celsius)"
        )

    async def test_resource_units_are_forwarded(self, client) -> None:
        contents = await client.read_resource("weather://Berlin?units=fahrenheit")
        assert contents[0].text.endswith("(fahrenheit)")


async def test_all_kinds_are_versioned(application) -> None:
    versions = {
        (str(v.version[0]), str(v.version[1]))
        for v in application.service.manager.list_versions()
    }
    assert ("search_weather", V1) in versions
    assert ("weather_briefing", V1) in versions
    assert ("weather_reading", V1) in versions
