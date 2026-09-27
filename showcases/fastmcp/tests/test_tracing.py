"""Tracing tests: assert the OTEL hook emits a span per migration step.

Uses an in-memory exporter instead of the OTLP one, so nothing leaves the
process. The container's ``tracer`` provider is overridden with the in-memory
tracer — the same wiring production uses, only the exporter differs.
"""

from __future__ import annotations

import pytest
from fastmcp_demo.container import (
    build_container,
    resolve_prepared,
    shutdown_container,
)
from fastmcp_demo.settings import DemoSettings, TelemetrySettings
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


@pytest.fixture
def span_exporter() -> InMemorySpanExporter:
    return InMemorySpanExporter()


@pytest.fixture
def in_memory_tracer(span_exporter: InMemorySpanExporter):
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    return provider.get_tracer("test")


@pytest.fixture
async def traced_service(in_memory_tracer):
    settings = DemoSettings(telemetry=TelemetrySettings(enabled=False))
    container = build_container(settings)
    container.tracer.override(in_memory_tracer)
    service = await resolve_prepared(container)
    yield service
    await shutdown_container(container)


@pytest.fixture
async def untraced_service():
    settings = DemoSettings(telemetry=TelemetrySettings(enabled=False))
    container = build_container(settings)
    container.tracer.override(None)
    service = await resolve_prepared(container)
    yield service
    await shutdown_container(container)


class TestTracing:
    async def test_one_span_per_migration_step(
        self, traced_service, span_exporter
    ) -> None:
        traced_service.demo_calls()
        spans = span_exporter.get_finished_spans()
        assert spans, "no spans were exported"
        assert all(span.name.endswith(".migrate") for span in spans)

    async def test_span_carries_migration_attributes(
        self, traced_service, span_exporter
    ) -> None:
        traced_service.demo_calls()
        span = span_exporter.get_finished_spans()[0]
        attrs = dict(span.attributes or {})
        assert attrs["migration.kind"] == "search_weather"
        assert "migration.from_version" in attrs
        assert "migration.to_version" in attrs
        assert "migration.duration_seconds" in attrs

    async def test_tracing_disabled_emits_nothing(
        self, untraced_service, span_exporter
    ) -> None:
        untraced_service.demo_calls()
        assert span_exporter.get_finished_spans() == ()
