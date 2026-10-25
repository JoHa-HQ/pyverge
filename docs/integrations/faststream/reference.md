# FastStream reference

## The seams

Both seams are decorators at the endpoint. Subscribers use `targets=`; publishers
use `target=`. Targets are resolved by the adapter, never by the core manager.

### `subscriber(broker, *topics, manager=..., targets=..., header=...)`

Registers one subscriber per topic with a convergence `decoder` and binds the
handler's typed payload parameter to the served version — or to a union when the
target can vary. Parsing stays FastStream's; pyverge only converges. Optional
`binder=` overrides how the parameter is bound.

`targets=` is either one policy for every topic or a `TopicTargets` mapping:

```python
from pyverge.adapters.faststream import TopicTargets

@subscriber(
    broker,
    "orders.v1",
    "orders.v2",
    manager=manager,
    targets=TopicTargets({
        "orders.v1": "1.0.0",
        "orders.v2": "latest",
    }),
)
async def handle(order: Order) -> None:
    ...
```

Unlisted topics fall back to `latest`.

#### Header negotiation

Set `header="accept-version"` (or another name) to let a message override the
topic target:

```python
@subscriber(broker, "orders.v1", manager=manager, header="accept-version")
async def handle(order: Order) -> None:
    ...
```

Accepted values: `1.0.0`, `latest`, `earliest`, `skip`, or a JSON per-kind map
such as `{"Order": "1.0.0"}`. Precedence is:

```text
message header > topic target > endpoint target
```

A union annotation is bound automatically when the target can vary across topics
or headers.

### `publisher(broker, *topics, manager=..., target=...)`

Registers a FastStream publisher and converges the handler's **return** to
`target` before publish. A handler that returns a bound model is dumped to a
payload and converged; a return without a resolvable `(kind, version)` is logged
and passed through unchanged.

Stacking `@subscriber(...)` over `@publisher(...)` gives an in/out bridge; the
in-target and out-target may differ.

### `publish_to(broker, routes={...}, manager=...)`

For different targets per destination, `publish_to` converges the handler's
return once per route and publishes separately. The handler returns the model
unchanged; the adapter owns dumping, convergence, and publishing:

```python
@subscriber(broker, "orders.v1", "orders.v2", manager=manager)
@publish_to(
    broker,
    routes={
        "orders.legacy": "1.0.0",
        "orders.current": "2.0.0",
    },
    manager=manager,
)
async def handle(order: Order) -> Order:
    return order
```

`manager.dump` runs once; each route then converges independently. The wrapper
publishes a `content-version` header with the served version.

## Routing

pyverge converges; it does not choose a transport. Because every payload leaves
convergence with an explicit `(kind, version)`, routing is deterministic.

Use `publish_to` when one handler must publish to destinations with different
target versions. The handler returns the model unchanged; the adapter dumps it
once, converges once per route, and publishes each result.

```python
@subscriber(
    broker,
    "orders.v1",
    "orders.v2",
    manager=manager,
    targets="latest",
)
@publish_to(
    broker,
    routes={
        "orders.legacy": "1.0.0",
        "orders.current": "2.0.0",
    },
    manager=manager,
)
async def handle_order(order: Order) -> Order:
    return order
```

This keeps routing declarative and removes manager/broker plumbing from the
handler. For a single outgoing target, keep using `@publisher(...)`.

## Registration

Models and migrations must be registered on the manager class before the runtime
instance is constructed. Subscribers bind their typed payload parameter at
decoration time. A subscriber whose typed parameter is not a provider model
(e.g. `dict`) is skipped. Union annotations are unwrapped to their first concrete
model.

## Target policy

`targets=` accepts pyverge's target policy: `"latest"` (default), `"earliest"`,
a pinned version, or a per-kind mapping (`{"Order": "1.0.0"}`).

- A scalar applies to every subscribed topic.
- `TopicTargets` applies a policy per topic.
- `header=` adds per-message negotiation, overriding both.
- Missing topic entries fall back to the endpoint default, `latest`.

Publishers keep `target=` for a single outgoing destination; use
`publish_to(routes=...)` for per-route targets.

## Identity and failure behavior

Convergence keys off the payload's own `(kind, version)`.

- **Missing/unknown identity** — logged as a warning; the payload passes through
  unchanged (no raise, no inference).
- **No migration path** — raises, so the message is not silently processed.
- **Unparsable body** — the decoder raises, rather than passing the raw body to
  the handler.

## See also

- [Managers](../../explanation/managers.md) — the bounded-context invariant the adapter relies on.
- [Migrations](../../explanation/migrations.md) — reconstructing missing models and migrations.
- [Target Policy](../../reference/target-policy.md) — `latest`/`earliest`/pinned/per-kind.
- [Telemetry & Hooks](../../how-to/operations/instrument-migrations.md) — per-step spans and call-level tracing.
