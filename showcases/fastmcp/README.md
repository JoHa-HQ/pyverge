# FastMCP + OpenTelemetry showcase

A runnable pyverge example: a versioned FastMCP server backed by the real
[Open-Meteo](https://open-meteo.com/) API, with an OpenTelemetry dashboard.

The version graph models the API's schema growing over time — v1 returned
`temperature`, v2 added `humidity`, v3 added `wind`. A call at any version
converges to the newest before the handler runs, and each migration step emits a
span to Jaeger.

## Run

```bash
cd showcases/fastmcp
uv sync
docker compose up -d            # otel-collector + jaeger
uv run python -m fastmcp_demo   # self-driving demo
```

Open the Jaeger UI at <http://localhost:16686> (service `pyverge-fastmcp-demo`)
to see the `pyverge-fastmcp-demo.call` span with one `…migrate` child per step.

## Connect to a code agent

The server speaks MCP over stdio. Add it to an agent (e.g. OpenCode) as a local
MCP server:

```jsonc
// opencode.json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "fastmcp-demo": {
      "type": "local",
      "command": ["uv", "run", "python", "-m", "fastmcp_demo", "--serve"],
      "environment": { "FASTMCP_DEMO_TELEMETRY__ENABLED": "false" }
    }
  }
}
```

Then ask the agent to call `search_weather` — at any schema version. Telemetry
is off here because stdio owns stdout; drop the env var to also export spans.

## Tests

```bash
uv run pytest
```

Offline end-to-end suite: a call at any registered version converges to the
anchor shape (Hypothesis draws the readings, Syrupy snapshots the shape), plus a
time-travel round-trip across versions. The app is built through its composition
root and driven via public interfaces only.
