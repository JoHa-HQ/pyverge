"""OpenTelemetry tracing adapter.

Builds a ``TracerProvider`` that exports spans over OTLP to the collector in
``docker-compose.yml``, and adapts the tracer to the two hooks the FastMCP
adapter consumes:

* :func:`make_migration_hooks` — the per-edge hooks attached by ``ToolRegistry``
  (one OTEL span per migration step),
* :func:`make_span_factory` — the call-level parent span the ``ConvergeMiddleware``
  opens, so every step span nests under the tool call.

This is the only module that imports the OpenTelemetry SDK — the rest of the app
depends on the returned objects alone.
"""

from __future__ import annotations

from collections.abc import Sequence

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from pyverge.adapters.otel import OTELHook
from pyverge.types import Attachable

from ..settings import TelemetrySettings


def build_tracer(settings: TelemetrySettings):
    """Return an OTLP-exporting tracer for *settings*.

    The provider is installed as the global tracer provider, so
    ``trace.get_tracer(...)`` anywhere in the process resolves to it.
    """
    resource = Resource.create({"service.name": settings.service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.otlp_endpoint, insecure=True)
        )
    )
    trace.set_tracer_provider(provider)
    return provider.get_tracer(settings.service_name)


def make_tracer(settings: TelemetrySettings):
    """Return a tracer when tracing is enabled, else ``None``.

    Used by the DI container so tests can disable the OTLP exporter without
    patching the adapter.
    """
    if not settings.enabled:
        return None
    return build_tracer(settings)


def make_migration_hooks(tracer, service: str) -> Sequence[Attachable]:
    """Return the per-edge hooks, or an empty list when tracing is off."""
    if tracer is None:
        return ()
    return (OTELHook(tracer=tracer, service=service),)


def make_span_factory(tracer, service: str):
    """Return a call-level parent-span factory, or ``None`` when tracing is off."""
    if tracer is None:
        return None

    def span_factory(name: str):
        return tracer.start_as_current_span(
            f"{service}.call", attributes={"tool": name}
        )

    return span_factory
