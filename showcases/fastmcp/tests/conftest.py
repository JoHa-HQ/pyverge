"""Shared fixtures for the showcase tests.

The demo runs with tracing disabled by default in tests, so no OTLP exporter is
built and no spans leave the process. Tests that assert on spans pass their own
in-memory tracer into ``DemoService``.
"""

from __future__ import annotations

import pytest
from fastmcp_demo.container import (
    build_container,
    resolve_prepared,
    shutdown_container,
)
from fastmcp_demo.settings import DemoSettings, TelemetrySettings


@pytest.fixture
def settings() -> DemoSettings:
    return DemoSettings(telemetry=TelemetrySettings(enabled=False))


@pytest.fixture
def container(settings: DemoSettings):
    return build_container(settings)


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
