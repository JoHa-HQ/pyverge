"""Infrastructure resources: broker, tracing, and their lifecycle.

Each managed resource is a generator: setup before ``yield``, teardown after.
``providers.Resource`` drives them via ``container.init_resources()`` /
``shutdown_resources()``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from pyverge.adapters.otel import OTELHook
from pyverge.types import Attachable


def build_tracer_provider(
    enabled: bool,
    service: str,
    endpoint: str,
) -> TracerProvider | None:
    """Return an OTLP-exporting provider, or ``None`` when tracing is disabled."""
    if not enabled:
        return None
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    return provider


def make_migration_hooks(
    provider: TracerProvider | None,
    service: str,
) -> Sequence[Attachable]:
    """Return the per-edge migration hooks, or nothing when tracing is off."""
    if provider is None:
        return ()
    return (OTELHook(tracer=provider.get_tracer(service), service=service),)


def tracer_resource(enabled: bool, service: str, endpoint: str) -> Iterator[Any]:
    """Resource: build the tracer provider, shut it down on teardown."""
    provider = build_tracer_provider(enabled, service, endpoint)
    try:
        yield provider
    finally:
        if provider is not None:
            provider.shutdown()


async def broker_resource(
    broker_cls: type,
    dsn: str | None,
    telemetry_cls: type,
    tracer: TracerProvider | None,
) -> AsyncIterator[Any]:
    """Resource: build the broker, attach telemetry when on, stop on teardown."""
    instance = broker_cls(dsn) if dsn else broker_cls()
    if tracer is not None:
        instance.add_middleware(telemetry_cls(tracer_provider=tracer))
    try:
        yield instance
    finally:
        await instance.stop()


__all__ = [
    "broker_resource",
    "build_tracer_provider",
    "make_migration_hooks",
    "tracer_resource",
]
