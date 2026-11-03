# Use the httpx transport with pyverge

## Prerequisites

- The HTTP adapter installed:

  ```bash
  pip install "pyverge[httpx]"
  ```

- A configured manager and `ConvergenceRuntime`.
- An HTTP service whose request or response body is JSON.

## Steps

### Build the runtime and policy

`HttpPolicy` holds the client-side strategy: one request target and an optional
response target.

```python
from pyverge.adapters.httpx import HttpPolicy
from pyverge.adapters.runtime import ConvergenceRuntime

runtime = ConvergenceRuntime(manager, manager.runtime().runner)
policy = HttpPolicy(target="latest", response_target="1.0.0")
```

### Create the transport

```python
from pyverge.adapters.httpx import PyvergeTransport

transport = PyvergeTransport(runtime, policy=policy)
```

The transport does not wrap the client. Pass it to an existing `httpx.Client`:

```python
import httpx

with httpx.Client(transport=transport) as client:
    response = client.post(
        "https://orders.example/orders",
        json=order_v1,
    )
    order = response.json()
```

The request body is converged to `latest` and sent with `content-version`. The
response body is converged to `1.0.0`, and the request carries
`accept-version: 1.0.0`.

### Use one policy per client

A transport sees outgoing requests, not remote handlers. It cannot infer a
handler-specific strategy, so use a separate client/transport for each policy:

```python
legacy = httpx.Client(
    transport=PyvergeTransport(
        runtime,
        policy=HttpPolicy(target="1.0.0", response_target="1.0.0"),
    )
)
current = httpx.Client(
    transport=PyvergeTransport(
        runtime,
        policy=HttpPolicy(target="latest", response_target="latest"),
    )
)

legacy.post(url, json=order_v2)  # v1 on the wire
current.post(url, json=order_v1)  # v2 on the wire
```

### Use HTTP/2

The transport is HTTP-version agnostic because it operates on `httpx.Request`
and `httpx.Response`. HTTP/2 protocol negotiation stays with httpx/httpcore:

```bash
pip install "httpx[http2]"
```

```python
with httpx.Client(http2=True, transport=transport) as client:
    ...
```

HTTP/2 carries the version headers per stream. The policy is still per client,
not per stream.

### Use the async transport

```python
from pyverge.adapters.httpx import PyvergeAsyncTransport

transport = PyvergeAsyncTransport(runtime, policy=policy)
async with httpx.AsyncClient(transport=transport) as client:
    response = await client.post(url, json=order_v1)
```

### Bind startup health

```python
transport.bind(manager.runtime().runner)
```

`bind` binds the runtime runner and validates registry health. Pass
`validate_health=False` for late registration, then call
`transport.runtime.validate_health()`.

## Verify

```python
response = client.post(url, json=order_v1)
assert response.json()["version"] == "1.0.0"
```

## Troubleshooting

- Request body unchanged: the body must be a JSON object with a JSON
  `content-type`.
- Response not converged: set `response_target` on the policy.
- Wrong target for an endpoint: create a separate client/transport for that
  policy.
- Import error: install `pyverge[httpx]`.

## See also

- [httpx integration model](index.md)
- [httpx reference](reference.md)
- [httpx showcase](https://github.com/JoHa-HQ/pyverge/tree/main/showcases/httpx)
