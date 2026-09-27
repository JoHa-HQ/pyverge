"""OpenTelemetry tracing adapter.

Builds a ``TracerProvider`` that exports spans over OTLP to the collector in
``docker-compose.yml``. This is the only module that imports the OpenTelemetry
SDK — the rest of the app depends on the returned tracer object alone.
"""

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

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
