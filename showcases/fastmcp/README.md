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

## Layout

```
showcases/fastmcp/
├── src/fastmcp_demo/
│   ├── settings.py             # pydantic-settings configuration tree
│   ├── container.py            # dependency-injector composition root
│   ├── domain/graph.py         # the version graph (no FastMCP, no OTEL)
│   ├── application/service.py  # DemoService + walk_topology use case
│   ├── adapters/server.py      # FastMCP server + registry + middleware
│   ├── adapters/tracing.py     # OTLP tracer builder
│   └── __main__.py             # CLI entry point
├── tests/                      # container, server, topology, tracing suites
├── migrations/                 # declarative JSON Patch specs (fwd + rev)
├── registry/weather.json       # the v3 anchor schema (reference)
├── docker-compose.yml          # otel-collector + jaeger
├── otel-collector-config.yaml  # collector pipeline: OTLP in -> Jaeger out
└── pyproject.toml              # the demo package
```

The layers are one-directional: `domain` knows nothing of FastMCP or
OpenTelemetry; `adapters` are the only modules that import them; `application`
orchestrates and `container` wires.

## Prerequisites

- Docker + Docker Compose (for the dashboard)
- The demo package: `cd showcases/fastmcp && uv sync`

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

## Testing

The suite is the reference for testing a version graph:

| Suite | Concern |
| --- | --- |
| `test_container.py` | the graph registers every version; only the anchor is concrete |
| `test_server.py` | reflection lifecycle; every version converges to the anchor |
| `test_topology.py` | the **time-travel round trip** (below) |
| `test_tracing.py` | one OTLP span per migration step, with the right attributes |

The **time-travel topology test** walks a newest-shaped payload down to the
oldest version and back up, asserting each hop yields the correctly-typed
container. It catches missing reverse edges, non-idempotent migrations, and
finalize drift — failures that per-edge unit tests miss. See
[Testing](../../docs/testing.md) for the general pattern.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `FASTMCP_DEMO_TELEMETRY__ENABLED` | `true` | Build the OTLP tracer |
| `FASTMCP_DEMO_TELEMETRY__OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC collector endpoint |
| `FASTMCP_DEMO_GRAPH__KIND` | `search_weather` | The versioned kind |

Disabling telemetry (`FASTMCP_DEMO_TELEMETRY__ENABLED=false`) keeps calls
converging with no span export — useful without the dashboard running.
