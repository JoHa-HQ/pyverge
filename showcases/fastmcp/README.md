# FastMCP + OpenTelemetry showcase

A runnable pyverge example: a versioned FastMCP server backed by the real
[Open-Meteo](https://open-meteo.com/) API, with an OpenTelemetry dashboard.

The demo exposes **three versioned kinds — one per FastMCP primitive type** — so
every reflection provider has a physical anchor, plus the nested `coordinates`
kind the tool embeds:

| Kind | Primitive | Graph |
| --- | --- | --- |
| `search_weather` | tool | v1 `temperature` → v2 `+humidity` → v3 `+wind` → v4 `+coordinates` |
| `coordinates` | nested | v1 `latitude`, `longitude` |
| `weather_briefing` | prompt | v1 `city` → v2 `+style` |
| `weather_reading` | resource | v1 `city` → v2 `+units` |

A call at any version converges to the anchor before the handler runs, and each
migration step emits a span to Jaeger. Tool, prompt, and resource calls all
negotiate the version natively (FastMCP's `version=`), routed to the materialized
virtual primitive.

## Run

```bash
cd showcases/fastmcp
uv sync
docker compose up -d            # otel-collector + jaeger
uv run python -m fastmcp_demo   # serves MCP over HTTP (port 8001; SERVER_PORT to override)
```

The server listens on `http://127.0.0.1:8001/mcp` (set `SERVER_PORT` if 8001 is
taken). Open the Jaeger UI at
<http://localhost:16686> (service `pyverge-fastmcp-demo`) to see the
`pyverge-fastmcp-demo.call` span with one `…migrate` child per step.

## Connect to a code agent

Add the HTTP MCP endpoint to an agent (e.g. OpenCode):

```jsonc
// opencode.json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "fastmcp-demo": {
      "type": "remote",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

Then ask the agent to call `search_weather` — at any schema version. The agent
sees one tool whose arguments are the v4 record; a call declaring an older
version converges upstream. Prompts (`weather_briefing`) and resources
(`weather://{city}`) behave the same way.

## Layout

- `domain/` — the version graph (anchor models, migration callables, manager).
  No FastMCP, no OpenTelemetry.
- `adapters/tools.py` — the physical primitives (tool, prompt, resource).
- `adapters/server.py` — the FastMCP server, discovery wiring, and the lifecycle.
- `adapters/tracing.py` — the OpenTelemetry tracer, the per-migration hooks, and a
  host-owned `CallSpanMiddleware`; tracing is the host's concern, not the
  adapter's.
- `container.py` — the `dependency-injector` composition root.

## Tests

```bash
uv run pytest
```

Offline end-to-end suite: a call at any registered version converges to the
anchor shape (Hypothesis draws the readings, Syrupy snapshots the shape). The app
is built through its composition root and driven via the public server API
in-process — no HTTP, no entry point.
