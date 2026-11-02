# httpx transport reference

## `HttpPolicy(target="latest", response_target=None)`

The client-side strategy for one HTTP boundary. `target` is the request payload
target; `response_target` optionally selects the response version. A policy is
reusable across sync and async transports for the same boundary.

## `PyvergeTransport(runtime, *, policy=None, transport=None)`

Synchronous `httpx.BaseTransport`. `runtime` is a `ConvergenceRuntime`;
`policy` defaults to `HttpPolicy()`; `transport` is the inner transport and
defaults to `httpx.HTTPTransport()`.

The transport uses one fixed strategy. It does not read targets from request
headers and does not route to remote handlers.

`handle_request(request)`:

- converges a JSON object body to `target`;
- rewrites `content-version` to the version actually sent;
- sets `accept-version` when `response_target` is a version string;
- converges a successful JSON response to `response_target`, when set;
- passes non-JSON and non-success traffic through.

`bind(runner, *, validate_health=True)` binds the runtime runner and validates
registry health.

`close()` closes the inner transport.

## `PyvergeAsyncTransport(...)`

Same surface with `handle_async_request` and `aclose`.

## Properties

- `runtime` — the `ConvergenceRuntime`.
- `policy` — the `HttpPolicy`.
- `transport` — the inner httpx transport.

## Header contract

- `content-version` — version actually sent for the request body.
- `accept-version` — requested response version, set from `response_target`.

The header names are part of the adapter's HTTP convention.
