"""Celery adapter composition: one runtime, one process backend, one chain.

The domain layer is injected through the manager. The adapter owns the Celery
app, the shared runtime, the process backend, the task targets, and optional
telemetry. Nothing here knows how migrations are implemented.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import semver
from celery import Celery, Task, chain
from opentelemetry import trace as otel_trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Tracer
from pyverge.execution import (
    OTELHook,
    OtelMiddleware,
    ProcessBackend,
    Runner,
)

from pyverge import Manager
from pyverge.adapters.celery import CeleryLifecycle, CeleryRuntime, task

from .domain import build_manager


@dataclass(frozen=True, slots=True)
class TelemetrySettings:
    """Opt-in OpenTelemetry configuration for the worker."""

    enabled: bool = False
    service_name: str = "pyverge-celery-demo"
    endpoint: str = "http://localhost:4317"


@dataclass(frozen=True, slots=True)
class CeleryDemo:
    """The assembled adapter: app, runtime, tasks, and an observable trace."""

    app: Celery
    manager: Manager[semver.Version]
    runtime: CeleryRuntime
    trace: list[tuple[str, dict[str, Any]]]
    ingest: Task
    enrich: Task
    publish: Task
    backend: ProcessBackend | None = None
    tracer_provider: TracerProvider | None = None

    def run(self, order: dict[str, Any]) -> dict[str, Any]:
        """Run the v1 -> v2 -> v3 chain and return the v3 result."""
        return (
            chain(self.ingest.s(order), self.enrich.s(), self.publish.s())
            .apply_async()
            .get()
        )

    def close(self) -> None:
        """Flush telemetry and close the process pool when this process owns it."""
        if self.tracer_provider is not None:
            self.tracer_provider.shutdown()
        if self.backend is not None:
            self.backend.close()


def _build_telemetry(
    settings: TelemetrySettings,
) -> tuple[TracerProvider, Tracer]:
    """Build an OTLP-exporting provider and its tracer."""
    provider = TracerProvider(
        resource=Resource.create({"service.name": settings.service_name})
    )
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=settings.endpoint, insecure=True))
    )
    otel_trace.set_tracer_provider(provider)
    return provider, provider.get_tracer(settings.service_name)


def _make_runner(
    manager: Manager[semver.Version],
    telemetry: TelemetrySettings,
) -> tuple[Runner, ProcessBackend, TracerProvider | None]:
    """Build the runner for one process: process pool plus optional telemetry."""
    middleware: tuple[Any, ...] = ()
    provider: TracerProvider | None = None
    if telemetry.enabled:
        provider, tracer = _build_telemetry(telemetry)
        manager.attach_hooks((OTELHook(tracer=tracer, service=telemetry.service_name),))
        middleware = (OtelMiddleware(tracer=tracer, service=telemetry.service_name),)
    backend = ProcessBackend(max_workers=2)
    runner = manager.runner(backend=backend, middleware=middleware)
    return runner, backend, provider


def build_demo(
    *,
    eager: bool = True,
    telemetry: TelemetrySettings | None = None,
) -> CeleryDemo:
    """Assemble the Celery app, runtime, and the versioned task chain.

    Eager mode binds immediately, so the demo and tests need no broker. A real
    worker binds in ``worker_process_init`` and validates the registry in each
    child process.
    """
    settings = telemetry or TelemetrySettings()
    if eager:
        broker, backend = "memory://", "cache+memory://"
    else:
        broker = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0")
        backend = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
    app = Celery("celery_demo", broker=broker, backend=backend)
    app.conf.task_always_eager = eager
    app.conf.task_eager_propagates = eager

    manager = build_manager()
    runtime = CeleryRuntime(manager)
    provider: TracerProvider | None = None
    backend: ProcessBackend | None = None
    if eager:
        runner, backend, provider = _make_runner(manager, settings)
        runtime.bind(runner)
    else:
        worker_state: dict[str, Any] = {}

        def runner_factory() -> Runner:
            runner, child_backend, child_provider = _make_runner(manager, settings)
            worker_state["backend"] = child_backend
            worker_state["provider"] = child_provider
            return runner

        def shutdown() -> None:
            child_provider = worker_state.pop("provider", None)
            if child_provider is not None:
                child_provider.shutdown()
            child_backend = worker_state.pop("backend", None)
            if child_backend is not None:
                child_backend.close()

        CeleryLifecycle(
            runtime,
            runner_factory,
            on_shutdown=shutdown,
        ).install()

    trace: list[tuple[str, dict[str, Any]]] = []

    @task(
        app,
        runtime=runtime,
        name="ingest",
        target="1.0.0",
        return_target="1.0.0",
        payload="order",
    )
    def ingest(order: dict[str, Any]) -> dict[str, Any]:
        trace.append(("ingest", dict(order)))
        return order

    @task(
        app,
        runtime=runtime,
        name="enrich",
        target="2.0.0",
        return_target="2.0.0",
        payload="order",
    )
    def enrich(order: dict[str, Any]) -> dict[str, Any]:
        trace.append(("enrich", dict(order)))
        return {**order, "currency": "EUR"}

    @task(
        app,
        runtime=runtime,
        name="publish",
        target="3.0.0",
        return_target="3.0.0",
        payload="order",
    )
    def publish(order: dict[str, Any]) -> dict[str, Any]:
        trace.append(("publish", dict(order)))
        return {**order, "status": "published"}

    return CeleryDemo(
        app=app,
        manager=manager,
        runtime=runtime,
        trace=trace,
        ingest=ingest,
        enrich=enrich,
        publish=publish,
        backend=backend,
        tracer_provider=provider,
    )


__all__ = ["CeleryDemo", "TelemetrySettings", "build_demo"]
