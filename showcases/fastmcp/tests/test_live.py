"""Live smoke test against the real Open-Meteo API.

Opt-in: skipped unless ``--live`` is passed or ``LIVE_WEATHER=1`` is set, so the
default suite stays offline and deterministic. The rest of the suite overrides
``weather_client`` with the fake; this one exercises the real client end to end.
"""

from __future__ import annotations

import pytest
from fastmcp_demo.container import (
    build_container,
    resolve_prepared,
    shutdown_container,
)
from fastmcp_demo.settings import DemoSettings, TelemetrySettings


@pytest.mark.live
async def test_live_forecast_returns_current_reading() -> None:
    container = build_container(
        DemoSettings(telemetry=TelemetrySettings(enabled=False))
    )
    try:
        service = await resolve_prepared(container)
        result = (await service.demo_calls())[0][1]
        assert result["city"] == "Berlin"
        assert isinstance(result["temperature"], float)
        assert isinstance(result["humidity"], int)
        assert isinstance(result["wind"], float)
    finally:
        await shutdown_container(container)
