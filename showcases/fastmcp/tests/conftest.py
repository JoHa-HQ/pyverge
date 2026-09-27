"""End-to-end fixtures for the showcase.

The application is built once through its public composition root
(``build_container`` + ``resolve_prepared``) and driven through public
interfaces only: the FastMCP server (``server.call_tool``) and the pyverge
manager (``manager.migrate``). Tests never reassemble internal wiring.

Offline by default: the weather client is overridden with an in-memory fake
whose reading is either pinned (parametrized) or drawn from a **Hypothesis
strategy**. Sync fixtures keep the async machinery out of the test bodies —
which also lets Hypothesis-driven tests (sync-only) drive the public surface.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
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


def offline_settings() -> DemoSettings:
    """Settings for the offline showcase app (no OTLP exporter)."""
    return DemoSettings(telemetry=TelemetrySettings(enabled=False))


class FakeWeatherClient:
    """In-memory stand-in for :class:`WeatherClient` returning a fixed reading."""

    def __init__(self, reading: CurrentWeather) -> None:
        self.reading = reading

    def current(self, city: str, *, units: str = "celsius") -> CurrentWeather:
        if city.lower() == "nowhere":
            raise CityNotFound(city)
        return self.reading

    def close(self) -> None:  # pragma: no cover - lifecycle parity
        return None


@contextmanager
def running_app(
    reading: CurrentWeather, settings: DemoSettings | None = None
) -> Iterator[Any]:
    """Build + prepare the app with *reading*, yielding it; shut down after.

    Synchronous so sync tests (including Hypothesis examples, which cannot use
    fixtures) can drive the public surface without touching the event loop.
    """
    container = build_container(settings or offline_settings())
    container.weather_client.override(FakeWeatherClient(reading))
    app = asyncio.run(resolve_prepared(container))
    try:
        yield app
    finally:
        asyncio.run(shutdown_container(container))


def call_tool(server: Any, name: str, arguments: dict) -> Any:
    """Invoke a server tool synchronously; the public call surface."""
    return asyncio.run(server.call_tool(name, arguments))


@pytest.fixture
def settings() -> DemoSettings:
    """Offline settings for the showcase app."""
    return offline_settings()


@pytest.fixture
def reading(request: pytest.FixtureRequest) -> CurrentWeather:
    """The fake client's reading; parametrize indirectly to pin one."""
    return getattr(request, "param", SNAPSHOT_READING)


@pytest.fixture
def app(reading: CurrentWeather, settings: DemoSettings) -> Iterator[Any]:
    """The composition root prepared end to end; yields the ready service."""
    with running_app(reading, settings) as application:
        yield application


@pytest.fixture
def server(app):
    """The ready FastMCP server — the public call surface."""
    return app.server


@pytest.fixture
def manager(app):
    """The registered version graph — the public pyverge surface."""
    return app.manager
