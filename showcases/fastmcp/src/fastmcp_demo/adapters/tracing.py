"""OpenTelemetry tracing adapter.

Builds a ``TracerProvider`` that exports spans over OTLP to the collector in
``docker-compose.yml``, and adapts the tracer to the two seams the app composes:

* :func:`make_migration_hooks` — the per-edge hooks attached by the discovery
  (one OTEL span per migration step),
* :class:`CallSpanMiddleware` — a host-owned FastMCP middleware that opens the
  call-level parent span, so every step span nests under the tool call.

Tracing is the host's concern, not the adapter's: ``CallSpanMiddleware`` wraps
the server's tool calls on its own. This is the only module that imports the
OpenTelemetry SDK — the rest of the app depends on the returned objects alone.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from fastmcp.server.middleware import Middleware
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from pyverge.adapters.otel import OTELHook
from pyverge.types import Attachable

from ..settings import TelemetrySettings

if TYPE_CHECKING:
    from fastmcp.server.middleware import MiddlewareContext
    from mcp.types import CallToolRequestParams


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


class CallSpanMiddleware(Middleware):
    """Open a parent span per tool call; nested step spans attach beneath it.

    A host-side observer, independent of the pyverge adapter: it wraps each
    ``tools/call`` in a span named ``<service>.call``, so the per-migration
    hooks (attached to the graph) nest their step spans underneath.
    """

    def __init__(self, tracer, service: str) -> None:
        self._tracer = tracer
        self._service = service

    async def on_call_tool(
        self,
        context: MiddlewareContext[CallToolRequestParams],
        call_next,
    ) -> Any:
        kind = context.message.name
        with self._tracer.start_as_current_span(
            f"{self._service}.call", attributes={"tool": kind}
        ):
            return await call_next(context)


def make_call_span_middleware(tracer, service: str):
    """Return a :class:`CallSpanMiddleware`, or ``None`` when tracing is off."""
    if tracer is None:
        return None
    return CallSpanMiddleware(tracer, service)
