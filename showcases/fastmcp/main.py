"""FastMCP integration showcase — versioned tools with an OTEL dashboard.

A self-contained example wiring three pyverge pieces into one runnable demo:

* :class:`~pyverge.adapters.fastmcp.ToolRegistry` — a FastMCP ``lifespan`` hook
  that reflects the physical versioned tools into their manager, precomputes
  convergence paths and materializes virtual tools for versions with no
  physical declaration.
* :class:`~pyverge.adapters.fastmcp.ConvergeMiddleware` — converges each call's
  arguments to the policy target before the handler runs.
* :class:`~pyverge.adapters.otel.OTELHook` — one span per migration step, sent
  over OTLP to the collector in ``docker-compose.yml`` and shown in Jaeger.

The **physical tool is its own anchor**: a tool declares ``version=...`` and its
signature is reflected into a versioned model. The customer registers migrations
*after* the anchors exist, so the engine reconstructs the older endpoint from
the anchor (``on_missing="reconstruct_model"``).

Run the dashboard, then the demo::

    docker compose up -d
    uv run python -m showcases.fastmcp.main            # self-driving demo
    uv run python -m showcases.fastmcp.main --serve    # run the MCP server

Open the Jaeger UI at http://localhost:16686 and look for the
``pyverge-fastmcp-demo`` service. The OTLP endpoint defaults to
``http://localhost:4317``; override with ``OTEL_EXPORTER_OTLP_ENDPOINT``.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import semver
from fastmcp import FastMCP
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

from pyverge import Manager
from pyverge.adapters.fastmcp import ConvergeMiddleware, ToolRegistry
from pyverge.adapters.otel import OTELHook
from pyverge.migration import (
    JsonPatchMigration,
    JsonSchemaModelAdapter,
    MigrationSettings,
)
from pyverge.types import ManagerMigrationKey

ROOT = Path(__file__).resolve().parent
MIGRATION_SPEC = ROOT / "migrations" / "weather_100_200.json"

SERVICE = "pyverge-fastmcp-demo"
KIND = "search_weather"
V1, V2 = "1.0.0", "2.0.0"


def configure_tracing(service: str = SERVICE):
    """Build a tracer provider that exports spans over OTLP to the collector.

    Returns the tracer. Set ``OTEL_EXPORTER_OTLP_ENDPOINT`` to point at a
    different collector; the default matches ``docker-compose.yml``.
    """
    endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    resource = Resource.create({"service.name": service})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=True))
    )
    trace.set_tracer_provider(provider)
    return provider.get_tracer(service)


def build_server():
    """Wire the manager, registry, middleware and server together.

    Returns ``(mcp, registry, manager)``. The migration and its tracing hook are
    registered in :func:`prepare` — after the physical anchors exist.
    """
    ToolManager = Manager[semver.Version].configure(
        MigrationSettings(
            direction="forward",
            on_missing_path="raise",
            on_missing="reconstruct_model",
        ),
        JsonSchemaModelAdapter(version_property="version", kind_property="kind"),
    )
    manager = ToolManager()

    registry = ToolRegistry(
        manager,
        policies={KIND: "latest"},
        fallback_policy=None,
    )

    mcp = FastMCP(
        "WeatherServer",
        middleware=[ConvergeMiddleware(registry)],
        lifespan=registry,
    )

    @mcp.tool(version=V2)
    def search_weather(
        city: str, units: str = "celsius", humidity: bool = False
    ) -> dict:
        """Search weather for a city (target: v2).

        A call against the v1 schema (via the virtual tool) converges to this
        v2 shape before the handler runs.
        """
        return {"city": city, "units": units, "humidity": humidity}

    return mcp, registry, manager


async def prepare(registry, mcp, manager, tracer=None) -> ManagerMigrationKey:
    """Materialize the physical anchors, then register the migration.

    The physical tool *is* the v2 anchor — its signature is reflected into a
    model. Only then can the engine reconstruct v1 from that anchor when the
    migration is registered. The tracing hook is attached once the edge exists.
    """
    await registry.search(mcp)
    await registry.register(mcp)
    key = ManagerMigrationKey(KIND, V1, V2)
    manager.store_migration(
        key,
        JsonPatchMigration(json.loads(MIGRATION_SPEC.read_text())).patch,
    )
    if tracer is not None:
        manager.add_hook(key, OTELHook(tracer=tracer, service=SERVICE))
    await registry.reconcile(mcp)
    await registry.enrich(mcp)
    return key


def _demo_calls(registry: ToolRegistry) -> None:
    """Drive a few convergent calls and print the results."""
    print(f"precomputed path {KIND}@{V1} -> {registry.path(KIND, V1)}")
    for label, version in (("v1 (virtual)", V1), ("v2 (physical)", V2)):
        delegate = registry.delegate(KIND, version)
        assert delegate is not None, f"no delegate for {version}"
        result = delegate(city="Berlin")
        print(f"  call {label:14s} -> {result}")


def main() -> None:
    tracer = configure_tracing()
    print(f"OTLP tracing enabled; open http://localhost:16686 (service {SERVICE})")

    mcp, registry, manager = build_server()
    asyncio.run(prepare(registry, mcp, manager, tracer))

    if "--serve" in sys.argv:
        print("Running the MCP server (Ctrl-C to stop)")
        mcp.run()
        return

    print("Self-driving demo — a v1 call converges to the v2 handler:")
    _demo_calls(registry)


if __name__ == "__main__":
    main()
