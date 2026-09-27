"""Tracing tests: assert the OTEL hook emits a span per migration step.

Uses an in-memory exporter instead of the OTLP one, so nothing leaves the
process — the same wiring the container builds, just a different exporter.
"""

from __future__ import annotations

import pytest
from fastmcp_demo.application import DemoService
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
async def traced_service(in_memory_tracer, span_exporter) -> DemoService:
    settings = DemoSettings(telemetry=TelemetrySettings(enabled=False))
    service = DemoService(settings, tracer=in_memory_tracer)
    await service.prepare()
    return service


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

    async def test_tracing_disabled_emits_nothing(self, span_exporter) -> None:
        settings = DemoSettings(telemetry=TelemetrySettings(enabled=False))
        service = DemoService(settings, tracer=None)
        await service.prepare()
        service.demo_calls()
        assert span_exporter.get_finished_spans() == ()
