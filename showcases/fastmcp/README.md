# FastMCP + OpenTelemetry showcase

A self-contained, runnable example of the pyverge FastMCP adapter with an
OpenTelemetry dashboard. It is laid out as a small layered application with
dependency injection, so the wiring is testable rather than a single script.

It shows four things end to end:

1. **Versioned tools** — a physical FastMCP tool declares `version=...`; the
   adapter reflects its signature into a versioned model (the *anchor*).
2. **Convergent calls** — virtual tools for older schemas are materialized, and
   every call's arguments converge to the policy target before the handler runs.
3. **A version graph** — a three-version chain (v1 → v2 → v3) with forward and
   reverse edges, reconstructed from the anchor.
4. **Observability** — each migration step emits an OTLP span, shipped to Jaeger
   through the OpenTelemetry Collector.

## Prerequisites

- Docker + Docker Compose (for the dashboard)
- The demo package: `cd showcases/fastmcp && uv sync`

## Layout

```
showcases/fastmcp/
├── src/fastmcp_demo/
│   ├── settings.py             # pydantic-settings configuration tree
│   ├── container.py            # dependency-injector composition root
│   ├── domain/
│   │   ├── graph.py            # the version graph (no FastMCP, no OTEL)
│   │   ├── weather.py          # WeatherService — the tool's business logic
│   │   └── weather.json        # the anchor schema (source of truth)
│   ├── application/service.py  # DemoService — the runnable use case
│   ├── adapters/
│   │   ├── server.py           # FastMCP server + registry + middleware
│   │   ├── tools.py            # the injected physical tool
│   │   └── tracing.py          # OTLP tracer builder
│   └── __main__.py             # CLI entry point
├── tests/                      # container, server, topology, snapshot, tracing
├── migrations/                 # declarative JSON Patch specs (fwd + rev)
├── docker-compose.yml          # otel-collector + jaeger
├── otel-collector-config.yaml  # collector pipeline: OTLP in -> Jaeger out
└── pyproject.toml              # the demo package
```

The layers are one-directional: `domain` knows nothing of FastMCP or
OpenTelemetry; `adapters` are the only modules that import them; `application`
orchestrates and `container` wires. The physical tool receives the
`WeatherService` through dependency-injector wiring (`@inject` + `Provide`), so
no component reaches for its own dependencies. The injected parameter is hidden
from the exposed signature — the physical tool signature *is* the anchor model,
so a stray parameter would break the adapter's contract reconciliation.

## Run

Start the dashboard:

```bash
cd showcases/fastmcp
docker compose up -d
```

Run the self-driving demo:

```bash
uv run python -m fastmcp_demo
```

Expected output:

```
OTLP tracing enabled; open http://localhost:16686 (service pyverge-fastmcp-demo)
Self-driving demo — older calls converge to the anchor handler:
  search_weather@1.0.0  -> {'city': 'Berlin', 'units': 'celsius', 'humidity': False, 'wind': 0.0}
  search_weather@2.0.0  -> {'city': 'Berlin', 'units': 'celsius', 'humidity': False, 'wind': 0.0}
  search_weather@3.0.0  -> {'city': 'Berlin', 'units': 'celsius', 'humidity': False, 'wind': 0.0}
Topology walk (time travel down and back):
  3.0.0  -> {... 'wind': 0.0}
  2.0.0  -> {... 'humidity': False}
  1.0.0  -> {...}
```

Open the Jaeger UI at <http://localhost:16686>, pick the
`pyverge-fastmcp-demo` service, and inspect the `pyverge-fastmcp-demo.migrate`
spans. Each carries the kind, from/to versions, duration and status.

Run the MCP server instead of the self-driving calls:

```bash
uv run python -m fastmcp_demo --serve
```

Run the tests:

```bash
uv run pytest
```

Tear the dashboard down:

```bash
docker compose down
```

## How it works

The **physical tool is its own anchor**. `search_weather` is declared once at
`version="3.0.0"`; the registry reflects its signature into a v3 model during
the `register` phase. The v1 and v2 models are never registered by hand — the
engine reconstructs them from the v3 anchor and the migration diffs
(`on_missing="reconstruct_model"`). The `enrich` phase then precomputes the
convergence paths and materializes virtual v1 and v2 tools. A call against any
version converges to v3 before the handler runs.

Tracing is attached per forward edge with `manager.add_hook(...)`. One span per
migration step flows over OTLP to the collector, which forwards traces to
Jaeger. The hook is an adapter (`pyverge.adapters.otel.OTELHook`), so the domain
layer stays free of OpenTelemetry.

The reflection lifecycle (search → register → reconcile → enrich) runs exactly
once, as a `dependency-injector` `AsyncResource` (`container.prepared`), so
`await resolve_prepared(container)` yields a ready service. The physical tool
gets its `WeatherService` from the container — the handler is a thin adapter
over testable domain logic.

## Testing

The suite is the reference for testing a version graph:

| Suite | Concern |
| --- | --- |
| `test_container.py` | DI wiring; the graph registers every version; only the anchor is concrete |
| `test_server.py` | reflection lifecycle; every version converges; injected tool param is hidden |
| `test_topology.py` | the **time-travel round trip** (below) |
| `test_schema_snapshot.py` | the **field surface** of every version, pinned by snapshot |
| `test_tracing.py` | one OTLP span per migration step, with the right attributes |

The **time-travel topology test** walks a newest-shaped payload down to the
oldest version and back up, asserting each hop yields the correctly-typed
container. It catches missing reverse edges, non-idempotent migrations, and
finalize drift — failures that per-edge unit tests miss. The helper
(`tests/topology.py`) is a test utility, not application code. See
[Testing](../../docs/testing.md) for the general patterns.

The **schema snapshot** pins each version's field surface. A schema change then
becomes a visible diff; `pytest --snapshot-update` rewrites only the changed
version.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `FASTMCP_DEMO_TELEMETRY__ENABLED` | `true` | Build the OTLP tracer |
| `FASTMCP_DEMO_TELEMETRY__OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC collector endpoint |
| `FASTMCP_DEMO_GRAPH__KIND` | `search_weather` | The versioned kind |

Disabling telemetry (`FASTMCP_DEMO_TELEMETRY__ENABLED=false`) keeps calls
converging with no span export — useful without the dashboard running.
