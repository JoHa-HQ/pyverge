# FastMCP + OpenTelemetry showcase

A self-contained, runnable example of the pyverge FastMCP adapter with an
OpenTelemetry dashboard. It shows three things end to end:

1. **Versioned tools** — a physical FastMCP tool declares `version=...`; the
   adapter reflects its signature into a versioned model (the *anchor*).
2. **Convergent calls** — a virtual tool for the older schema is materialized,
   and every call's arguments converge to the policy target before the handler
   runs.
3. **Observability** — each migration step emits an OTLP span, shipped to Jaeger
   through the OpenTelemetry Collector.

## Layout

```
showcases/fastmcp/
├── main.py                     # the demo (server wiring + self-driving calls)
├── docker-compose.yml          # otel-collector + jaeger
├── otel-collector-config.yaml  # collector pipeline: OTLP in -> Jaeger out
├── migrations/weather_100_200.json  # v1 -> v2 declarative migration spec
└── registry/weather.json       # the v2 schema (reference)
```

## Prerequisites

- Docker + Docker Compose (for the dashboard)
- The `fastmcp` extra: `uv sync --extra fastmcp` (or `pip install "pyverge[fastmcp]"`)

## Run

Start the dashboard:

```bash
cd showcases/fastmcp
docker compose up -d
```

Run the self-driving demo (a v1 call converges to the v2 handler):

```bash
uv run python -m showcases.fastmcp.main
```

Expected output:

```
OTLP tracing enabled; open http://localhost:16686 (service pyverge-fastmcp-demo)
Self-driving demo — a v1 call converges to the v2 handler:
precomputed path search_weather@1.0.0 -> 2.0.0
  call v1 (virtual)   -> {'city': 'Berlin', 'units': 'celsius', 'humidity': False}
  call v2 (physical)  -> {'city': 'Berlin', 'units': 'celsius', 'humidity': False}
```

Open the Jaeger UI at <http://localhost:16686>, pick the
`pyverge-fastmcp-demo` service, and inspect the `pyverge-fastmcp-demo.migrate`
span. It carries the kind, from/to versions, duration and status.

To run the MCP server instead of the self-driving calls:

```bash
uv run python -m showcases.fastmcp.main --serve
```

Tear the dashboard down:

```bash
docker compose down
```

## How it works

The **physical tool is its own anchor**. `search_weather` is declared once at
`version="2.0.0"`; the registry reflects its signature into a v2 model during
the `register` phase. The migration is registered *after* that, so the engine
reconstructs the v1 endpoint from the v2 anchor and the migration diff
(`on_missing="reconstruct_model"`). The `enrich` phase then precomputes the
convergence path and materializes a virtual v1 tool. A call against v1 converges
to v2 before the handler runs.

The tracing hook is attached to the `search_weather 1.0.0 -> 2.0.0` edge with
`manager.add_hook(...)`. One span per migration step flows over OTLP to the
collector, which forwards traces to Jaeger.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC collector endpoint |

The demo runs even without the dashboard: if the collector is unreachable, calls
still converge — only the span export fails.
