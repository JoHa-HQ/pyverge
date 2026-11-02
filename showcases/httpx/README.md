# httpx transport + pyverge showcase

A versioned HTTP client that converges both directions:

```text
client sends Order v1
  -> PyvergeTransport converges to v2
  -> wire request: Order v2 + content-version: 2.0.0
  -> service responds: Order v2
  -> PyvergeTransport converges to v1 + accept-version: 1.0.0
  -> client reads Order v1
```

The local HTTP service is deliberately plain: it records the request and answers
with its own v2 contract. All convergence happens in the httpx transport.

## What it demonstrates

| Concern | Where |
| --- | --- |
| Pure version graph | `domain.py` |
| Versioned HTTP service | `server.py` |
| Runtime + transport composition | `client.py` |
| One strategy per client | `HttpPolicy(target=..., response_target=...)` |
| Request convergence | JSON body before the inner transport |
| Response convergence | successful JSON response before the client returns |
| Startup health | `transport.bind(manager.runner())` |
| Sync and async | `PyvergeTransport` and `PyvergeAsyncTransport` |

## Architecture

```text
domain.py    Order v1/v2 models, migrations, Manager
server.py    a plain versioned HTTP service, no pyverge imports
client.py    ConvergenceRuntime + PyvergeTransport composition
__main__.py  demo entrypoint
tests/       end-to-end sync and async transport tests
```

The domain has no HTTP imports. The server has no pyverge imports. The client
module is the adapter boundary: it builds the runtime, binds the runner, and
attaches one `HttpPolicy` to one transport.

A transport sees outgoing requests, not remote handlers, so it cannot infer a
handler-specific strategy. Use one transport/client per boundary. This showcase
uses two policies to show that explicitly:

- `latest -> 1.0.0` for a legacy caller;
- `1.0.0 -> latest` for a caller that sends old payloads.

## Run the demo

```bash
cd showcases/httpx
uv sync
uv run python -m httpx_demo
```

The output shows the client's v1 payload, the v2 request the server actually
received (with `content-version: 2.0.0`), and the v1 response the client read.

## HTTP/2

The transport is HTTP-version agnostic: it receives `httpx.Request` and
`httpx.Response`, so `httpx.Client(http2=True)` works when httpx's HTTP/2 extra
is installed:

```bash
uv add "httpx[http2]"
```

HTTP/2 protocol negotiation (ALPN, streams, framing) is handled by
httpx/httpcore. pyverge's application-level negotiation remains
`content-version`/`accept-version`.

One `HttpPolicy` is fixed per transport, so all HTTP/2 streams through one client
share it. Use separate clients for different policies; pyverge does not select a
strategy per stream or per remote handler.

```python
from pyverge.adapters.httpx import HttpPolicy

legacy = httpx.Client(
    http2=True,
    base_url=BASE_URL,
    transport=build_transport(
        manager,
        HttpPolicy(target="1.0.0", response_target="1.0.0"),
    ),
)
current = httpx.Client(
    http2=True,
    base_url=BASE_URL,
    transport=build_transport(
        manager,
        HttpPolicy(target="latest", response_target="latest"),
    ),
)

legacy.post("/orders", json=order_v2)  # v1 on the wire
current.post("/orders", json=order_v1)  # v2 on the wire
```

Each client owns its own HTTP/2 connection pool and policy. The headers travel
per stream; the policy is selected by the client.

## Tests

```bash
cd showcases/httpx
uv run pytest
```

The tests start the service on an ephemeral localhost port, drive a real
`httpx.Client`/`AsyncClient` through the public transport, and assert both the
wire payload and the client result. No external network is required.

## Design notes

- **Single responsibility** — the domain owns versions and migrations; the
  server owns its v2 contract; the client owns HTTP strategy.
- **Dependency inversion** — the transport depends on `ConvergenceRuntime`; the
  domain depends on neither.
- **Open/closed** — add a policy and a client for a new boundary without changing
  the transport or the domain.
- **One strategy per transport** — no per-request negotiation and no remote
  handler routing. The strategy is fixed before the client is created.
