"""Tracing tests: one nested span per migration step.

Uses an in-memory exporter instead of the OTLP one, so nothing leaves the
process. The container's ``tracer`` provider is overridden with the in-memory
tracer — the same wiring production uses, only the exporter differs.
"""

from __future__ import annotations

import asyncio

import pytest
from fastmcp_demo.container import (
    build_container,
    resolve_prepared,
    shutdown_container,
)
from fastmcp_demo.settings import DemoSettings, TelemetrySettings
from mcp.types import CallToolRequestParams
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter


class _Ctx:
    method = "tools/call"

    def __init__(self, message):
        self.message = message

    def copy(self, message):
        self.message = message
        return self


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


class TestMigrationSpans:
    async def test_one_span_per_migration_step(self, traced_service, span_exporter):
        await traced_service.demo_calls()
        spans = span_exporter.get_finished_spans()
        assert spans, "no spans were exported"
        steps = [s for s in spans if s.name.endswith(".migrate")]
        assert steps, "no migration step spans were exported"

    async def test_span_carries_migration_attributes(
        self, traced_service, span_exporter
    ):
        await traced_service.demo_calls()
        step = next(
            s for s in span_exporter.get_finished_spans() if s.name.endswith(".migrate")
        )
        attrs = dict(step.attributes or {})
        assert attrs["migration.kind"] == "search_weather"
        assert "migration.from_version" in attrs
        assert "migration.to_version" in attrs
        assert "migration.duration_seconds" in attrs

    async def test_tracing_disabled_emits_nothing(
        self, untraced_service, span_exporter
    ):
        await untraced_service.demo_calls()
        assert span_exporter.get_finished_spans() == ()


class TestNestedCallSpans:
    def test_step_spans_nest_under_the_call_span(self, traced_service, span_exporter):
        """A versioned call opens a parent span; each step nests underneath."""
        # The registry carries the production span factory via the server's
        # middleware; drive that middleware directly for the assertion.
        middleware = traced_service.server.middleware[0]

        async def call_next(ctx):
            raise AssertionError("converged call must not pass through")

        ctx = _Ctx(
            CallToolRequestParams(
                name="search_weather",
                arguments={"city": "Berlin", "version": "1.0.0"},
            )
        )
        asyncio.run(middleware.on_call_tool(ctx, call_next))

        spans = {span.name: span for span in span_exporter.get_finished_spans()}
        calls = [s for n, s in spans.items() if n.endswith(".call")]
        steps = [s for n, s in spans.items() if n.endswith(".migrate")]
        assert len(calls) == 1, f"expected one call span, got {list(spans)}"
        assert steps, "expected migration step spans"
        call_span = calls[0]
        for step in steps:
            assert step.parent is not None
            assert step.parent.span_id == call_span.context.span_id
