"""Shared fixtures for the showcase tests.

Tests run offline: ``weather_client`` is overridden with a deterministic fake,
so no call leaves the process. Tracing is disabled by default; span tests pass
their own in-memory tracer. This is the DI payoff — the real client is swapped
at the composition root, not patched deep inside.
"""

from __future__ import annotations

import os

import pytest
from fastmcp_demo.container import (
    build_container,
    resolve_prepared,
    shutdown_container,
)
from fastmcp_demo.domain import CityNotFound, CurrentWeather
from fastmcp_demo.settings import DemoSettings, TelemetrySettings


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run tests marked 'live' against the real Open-Meteo API.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "live: hits the real Open-Meteo API (opt-in via --live)."
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip ``live`` tests unless ``--live`` (or ``LIVE_WEATHER=1``) is set."""
    if config.getoption("--live") or os.environ.get("LIVE_WEATHER"):
        return
    skip = pytest.mark.skip(reason="live API test — run with --live")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


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
def manager(container):
    """The registered version graph, built by the DI container."""
    return container.manager()


@pytest.fixture
async def prepared(container):
    """A container whose reflection lifecycle has run once, yielding the service."""
    service = await resolve_prepared(container)
    yield service
    await shutdown_container(container)
