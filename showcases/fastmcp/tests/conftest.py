"""End-to-end fixtures for the showcase.

The application is built through its public composition root
(``build_container`` → ``resolve_prepared``) and driven through a FastMCP
``Client``. The discovery lifecycle runs as the server's **lifespan**, which
FastMCP enters only when the server is driven through a client — so the
``application`` fixture opens one session and keeps it active, and the ``client``
fixture hands that session to the test.

Offline by default: the weather client is overridden with an in-memory fake
whose reading is either pinned (parametrized) or drawn from a **Hypothesis
strategy**; it stays mutable, so a Hypothesis example can set a fresh reading.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastmcp import Client
from fastmcp_demo.container import (
    build_container,
    resolve_prepared,
    shutdown_container,
)
from fastmcp_demo.domain import CityNotFound, CurrentWeather
from fastmcp_demo.settings import DemoSettings, TelemetrySettings
from hypothesis import strategies as st

#: Arbitrary valid current-conditions reading.
weather_reading = st.builds(
    CurrentWeather,
    temperature=st.floats(min_value=-60, max_value=60, allow_nan=False),
    humidity=st.integers(min_value=0, max_value=100),
    wind=st.floats(min_value=0, max_value=200, allow_nan=False),
)

#: A readable reading pinned for the snapshot tests (parametrized indirectly).
SNAPSHOT_READING = CurrentWeather(temperature=21.5, humidity=58, wind=12.0)


class FakeWeatherClient:
    """In-memory stand-in for :class:`WeatherClient` returning a fixed reading.

    The reading is mutable, so a Hypothesis example can swap it before calling.
    """

    def __init__(self, reading: CurrentWeather) -> None:
        self.reading = reading

    def current(self, city: str, *, units: str = "celsius") -> CurrentWeather:
        if city.lower() == "nowhere":
            raise CityNotFound(city)
        return self.reading

    def close(self) -> None:  # pragma: no cover - lifecycle parity
        return None


@dataclass
class Application:
    """A ready app: the service, its live client session, and the weather fake."""

    service: Any
    client: Client
    weather: FakeWeatherClient


@pytest.fixture
def settings() -> DemoSettings:
    """Offline settings for the showcase app (no OTLP exporter)."""
    return DemoSettings(telemetry=TelemetrySettings(enabled=False))


@pytest.fixture
def reading(request: pytest.FixtureRequest) -> CurrentWeather:
    """The fake client's reading; parametrize indirectly to pin one."""
    return getattr(request, "param", SNAPSHOT_READING)


@pytest.fixture
async def application(
    reading: CurrentWeather, settings: DemoSettings
) -> AsyncIterator[Application]:
    """The composition root, prepared with a live client session.

    Entering the client runs the server lifespan (the discovery lifecycle), so
    the materialized tool, prompt, and resource primitives are servable for the
    duration of the test.
    """
    container = build_container(settings)
    weather = FakeWeatherClient(reading)
    container.weather_client.override(weather)
    service = await resolve_prepared(container)
    try:
        async with Client(service.server) as client:
            yield Application(service=service, client=client, weather=weather)
    finally:
        await shutdown_container(container)


@pytest.fixture
async def client(application: Application) -> Client:
    """The app's live client session — the public call surface."""
    return application.client
