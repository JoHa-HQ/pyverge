# FastMCP + OpenTelemetry showcase

A self-contained, runnable example of the pyverge FastMCP adapter with an
OpenTelemetry dashboard, backed by the **real Open-Meteo API**. It is laid out
as a small layered application with dependency injection, so the wiring is
testable rather than a single script.

It shows four things end to end:

1. **Versioned tools** — a physical FastMCP tool declares `version=...`; the
   adapter reflects its signature into a versioned model (the *anchor*).
2. **Convergent calls** — virtual tools for older schemas are materialized, and
   every call's arguments converge to the policy target before the handler runs.
3. **A version graph modelling a real API's evolution** — the Open-Meteo
   response grew over time: v1 returned `temperature`, v2 added `humidity`, v3
   added `wind`. Forward and reverse migration edges let a payload from any
   version converge.
4. **Observability** — each migration step emits an OTLP span, shipped to Jaeger
   through the OpenTelemetry Collector.

The tool is keyless: it geocodes the city and reads current conditions from
[Open-Meteo](https://open-meteo.com/).

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
│   │   ├── migrations.py       # Python callable migration edges (fwd + rev)
│   │   ├── models.py           # SearchWeather — the anchor Pydantic model
│   │   └── weather.py          # WeatherClient (Open-Meteo) + WeatherService
│   ├── application/service.py  # DemoService — the runnable use case
│   ├── adapters/
│   │   ├── server.py           # FastMCP server + registry + middleware
│   │   ├── tools.py            # the injected physical tool (built via make_tool)
│   │   └── tracing.py          # OTLP tracer builder
│   └── __main__.py             # CLI entry point
├── tests/                      # tool convergence + topology (end-to-end)
├── docker-compose.yml          # otel-collector + jaeger
├── otel-collector-config.yaml  # collector pipeline: OTLP in -> Jaeger out
└── pyproject.toml              # the demo package
```

The layers are one-directional: `domain` knows nothing of FastMCP or
OpenTelemetry; `adapters` are the only modules that import them; `application`
orchestrates and `container` wires. The physical tool receives the
`WeatherService` through dependency-injector wiring (`@inject` + `Provide`), so
no component reaches for its own dependencies. The adapter recognizes the
`Provide` marker and excludes the injected parameter from the reflected schema
and the reconciled contract — no signature rewrite needed, just annotate the
injected parameter `Any`.

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
  search_weather@1.0.0  -> {'city': 'Berlin', 'units': 'celsius', 'temperature': 16.0, 'humidity': 58, 'wind': 12.1}
  search_weather@2.0.0  -> {'city': 'Berlin', 'units': 'celsius', 'temperature': 16.0, 'humidity': 58, 'wind': 12.1}
  search_weather@3.0.0  -> {'city': 'Berlin', 'units': 'celsius', 'temperature': 16.0, 'humidity': 58, 'wind': 12.1}
```

Values are live from Open-Meteo, so the numbers vary per run.

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

The **anchor is a Pydantic model** (`domain/models.py`), registered with the
`PydanticModelAdapter`. The physical tool `search_weather` is declared once at
`version="3.0.0"` with a signature matching that model. The v1 and v2 models are
never registered by hand — the engine reconstructs them from the v3 anchor and
the migration diffs (`on_missing="reconstruct_model"`). The `enrich` phase then
precomputes the convergence paths and materializes virtual v1 and v2 tools. A
call against any version converges to v3 before the handler runs.

The version chain models the **Open-Meteo response schema growing over time**:
v1 carried `temperature`, v2 added `humidity`, v3 added `wind`. The edges are
**plain Python callables** (`domain/migrations.py`): the engine parses each
function's AST to reconstruct the older model, and runs it to migrate the
payload. A caller sending a v1-shaped payload has the missing fields filled by
the forward migrations before the handler refreshes them from the live API.

Tracing is wired at the composition root: the `ToolRegistry` receives the OTEL
hook and attaches it to **every** migration edge, while the `ConvergeMiddleware`
opens a parent span per call. One span per migration step then **nests** under
the call span, and the whole trace flows over OTLP to the collector and into
Jaeger. The hook is an adapter (`pyverge.adapters.otel.OTELHook`), so the domain
layer stays free of OpenTelemetry.

The reflection lifecycle (search → register → reconcile → enrich) runs exactly
once, as a `dependency-injector` `AsyncResource` (`container.prepared`), so
`await resolve_prepared(container)` yields a ready service. The physical tool
gets its `WeatherService` from the container, which in turn gets a
`WeatherClient` — the handler is a thin adapter over testable domain logic, and
tests swap the client for a fake at the composition root.

## Testing

The suite is deliberately small and **end-to-end**: the application is built
once through its composition root, and tests drive it through public interfaces
only — the FastMCP server (`server.call_tool`) and the pyverge manager
(`manager.migrate`). No internal wiring is reassembled by tests.

| Suite | Concern |
| --- | --- |
| `test_tool.py` | a call at any registered version converges to the anchor shape |
| `test_topology.py` | the **time-travel round trip**, parametrized per version |

The **time-travel topology test** walks a newest-shaped payload down to the
oldest version and back up, asserting each hop yields the correctly-typed
container. It catches missing reverse edges, non-idempotent migrations, and
finalize drift — failures that per-edge unit tests miss. It is **parametrized
per version**, so each schema change is a named case. The helper
(`tests/topology.py`) is a test utility, not application code. See
[Testing](../../docs/testing.md) for the general patterns.

The suite is offline: `weather_client` is overridden with a fake at the
composition root. Live checks run through the demo CLI
(`uv run python -m fastmcp_demo`) against the real Open-Meteo API.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `FASTMCP_DEMO_TELEMETRY__ENABLED` | `true` | Build the OTLP tracer |
| `FASTMCP_DEMO_TELEMETRY__OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC collector endpoint |
| `FASTMCP_DEMO_GRAPH__KIND` | `search_weather` | The versioned kind |

Disabling telemetry (`FASTMCP_DEMO_TELEMETRY__ENABLED=false`) keeps calls
converging with no span export — useful without the dashboard running.
