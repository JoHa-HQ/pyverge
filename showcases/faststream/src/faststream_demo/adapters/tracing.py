"""OpenTelemetry tracing adapter (host-owned).

Builds a ``TracerProvider`` that exports spans over OTLP to the collector in
``docker-compose.yml``, and adapts it to the seam the app composes:
:func:`make_migration_hooks` — the per-edge :class:`OTELHook` attached to the
manager, so each migration step emits a span.

The parent consume span comes from FastStream's own OpenTelemetry middleware
(attached in :mod:`.broker`), so step spans nest under it. Tracing is the host's
concern, not the adapter's: the pyverge adapter emits no spans. This is the only
module that imports the OpenTelemetry SDK.
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


def build_tracer_provider(settings: TelemetrySettings) -> TracerProvider | None:
    """Return an OTLP-exporting provider, or ``None`` when tracing is disabled.

    The provider is installed as the global tracer provider, so FastStream's
    telemetry middleware and ``trace.get_tracer(...)`` resolve to it.
    """
    if not settings.enabled:
        return None
    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.service_name})
    )
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=settings.otlp_endpoint, insecure=True)
        )
    )
    trace.set_tracer_provider(provider)
    return provider


def make_migration_hooks(
    provider: TracerProvider | None,
    service: str,
) -> Sequence[Attachable]:
    """Return the per-edge migration hooks, or an empty list when tracing is off."""
    if provider is None:
        return ()
    return (OTELHook(tracer=provider.get_tracer(service), service=service),)


__all__ = ["build_tracer_provider", "make_migration_hooks"]
