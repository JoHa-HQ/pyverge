# httpx transport

`PyvergeTransport` and `PyvergeAsyncTransport` make payload convergence the
transport inside an existing `httpx` client. The client, its configuration, and
its public API stay unchanged.

```bash
pip install "pyverge[httpx]"
```

## The model

A transport sits at the outbound HTTP boundary.

- **Transport** — `PyvergeTransport` implements `httpx.BaseTransport`;
  `PyvergeAsyncTransport` implements `httpx.AsyncBaseTransport`.
- **Policy** — one `HttpPolicy` holds the request target and optional response
  target for that boundary.
- **Request convergence** — JSON request bodies converge before the inner
  transport sends them.
- **Response convergence** — successful JSON responses converge before the
  client returns them.
- **Headers** — `content-version` reports the version actually sent;
  `accept-version` requests the response version.

## One strategy per transport

A transport sees outgoing requests, not remote handlers. It cannot infer a
handler-specific target. Use one transport/client per strategy; pyverge does not
route between the request and a remote handler.

Different endpoint strategies therefore use separate clients:

```python
legacy = httpx.Client(transport=legacy_transport)
current = httpx.Client(transport=current_transport)
```

Each client owns its own connection pool and policy.

## HTTP/2

The transport is HTTP-version agnostic. `httpx.Client(http2=True)` works when
httpx's HTTP/2 extra is installed. HTTP/2 protocol negotiation belongs to
httpx/httpcore; pyverge's application-level negotiation remains
`content-version` and `accept-version`. The policy stays per client, not per
stream.

## Use it

- [httpx how-to](how-to.md)
- [httpx reference](reference.md)
- [httpx showcase](https://github.com/JoHa-HQ/pyverge/tree/main/showcases/httpx)
