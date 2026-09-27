"""End-to-end fixtures for the showcase.

The application is built once through its public composition root
(``build_container`` + ``resolve_prepared``) and driven through public
interfaces only: the FastMCP server (``server.call_tool``) and the pyverge
manager (``manager.migrate``). Tests never reassemble internal wiring.

Offline by default: the weather client is overridden with a deterministic fake
at the container, so no call leaves the process.
"""

from __future__ import annotations

import pytest
from fastmcp_demo.container import (
    build_container,
    resolve_prepared,
    shutdown_container,
)
from fastmcp_demo.domain import CityNotFound, CurrentWeather
from fastmcp_demo.settings import DemoSettings, TelemetrySettings

#: Deterministic reading the fake client returns.
FAKE_READING = CurrentWeather(temperature=21.5, humidity=58, wind=12.0)


class FakeWeatherClient:
    """In-memory stand-in for :class:`WeatherClient`."""

    def __init__(self, reading: CurrentWeather = FAKE_READING) -> None:
        self._reading = reading

    def current(self, city: str, *, units: str = "celsius") -> CurrentWeather:
        if city.lower() == "nowhere":
            raise CityNotFound(city)
        return self._reading

    def close(self) -> None:  # pragma: no cover - lifecycle parity
        return None


@pytest.fixture
def settings() -> DemoSettings:
    return DemoSettings(telemetry=TelemetrySettings(enabled=False))


@pytest.fixture
def fake_client() -> FakeWeatherClient:
    return FakeWeatherClient()


@pytest.fixture
def container(settings: DemoSettings, fake_client: FakeWeatherClient):
    c = build_container(settings)
    c.weather_client.override(fake_client)
    return c


@pytest.fixture
async def app(container):
    """The composition root prepared end to end; yields the ready service."""
    service = await resolve_prepared(container)
    yield service
    await shutdown_container(container)


@pytest.fixture
def server(app):
    """The ready FastMCP server — the public call surface."""
    return app.server


@pytest.fixture
def manager(app):
    """The registered version graph — the public pyverge surface."""
    return app.manager
