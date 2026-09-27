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
uv run python -m fastmcp_demo   # serves MCP over HTTP
```

The server listens on `http://127.0.0.1:8000/mcp`. Open the Jaeger UI at
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
sees one tool whose arguments are the v3 record; a call declaring an older
version converges upstream.

## Tests

```bash
uv run pytest
```

Offline end-to-end suite: a call at any registered version converges to the
anchor shape (Hypothesis draws the readings, Syrupy snapshots the shape). The
app is built through its composition root and driven via the public server API
in-process — no HTTP, no entry point.
