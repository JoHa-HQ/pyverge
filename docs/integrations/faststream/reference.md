# FastStream reference

## The seams

Both seams are decorators at the endpoint. Subscribers use `targets=`; publishers
use `target=`. Targets are resolved by the adapter, never by the core manager.

A target may be `"latest"`, `"earliest"`, a pinned version, a per-kind mapping,
or a `VersionRange`. A range resolves to the highest matching version:

```python
from pyverge.adapters.faststream import FastStreamRuntime
from pyverge.runtime.manager.types import VersionRange

runtime = FastStreamRuntime(manager, manager.runtime().runner)

@subscriber(broker, "orders", runtime=runtime, targets=VersionRange(gte="1.0.0", lt="2.0.0"))
async def handle(order: OrderV2) -> None: ...
```

The negotiated header form is `{"gte": "1.0.0", "lt": "2.0.0"}` (or `eq`).

### `PyvergeBroker(broker, manager=None, *, runtime=None, runner=None, binder=None)`

Composition facade over any FastStream broker. It exposes `subscriber`,
`publisher`, and `publish_to`; owns one runtime and one binder; and records
decoration-time `Binding` metadata.

```python
from pyverge.adapters.faststream import PyvergeBroker

raw_broker = ...  # any FastStream broker
broker = PyvergeBroker(
    raw_broker,
    manager=manager,
    runner=manager.runtime().runner,
)

@broker.subscriber("orders", target="latest")
async def on_order(order: OrderV2) -> None: ...

@broker.subscriber("orders.in")
@broker.publisher("orders.v1", target="1.0.0")
async def relay(order: OrderV2) -> OrderV2: ...
```

- `broker.underlying` is the wrapped broker.
- Unknown attributes proxy to it (`publish`, `start`, `publishers`, …).
- `broker.bindings` exposes the recorded `Binding` values.
- FastStream's in-memory test broker works unchanged.

### Runtime lifecycle

The runtime never creates a runner implicitly. Build the runner with the host
application's execution environment and bind it during startup:

```python
from pyverge.adapters.faststream import FastStreamRuntime

runtime = FastStreamRuntime(manager)
broker = PyvergeBroker(broker, runtime=runtime)

async def start() -> None:
    runtime.bind(
        manager.runtime(
            backend=backend,
            environment=execution_environment,
            middleware=middleware,
        ).runner
    )
```

`converge()` raises if no runner is bound. Pass `manager=...` (and optionally
`runner=...`) to the facade to create its runtime, or pass `runtime=...` to share
one. The facade derives the manager from the runtime when `runtime=` is used.
Use `runtime.bind(...)` when the runner depends on the FastStream application
lifespan (telemetry, transport constraints, middleware).

`bind()` validates the registry before the app starts and raises FastStream's
`StartupValidationError` when an issue meets the fail level. The default is
`"error"`; `FastStreamRuntime(..., health_fail_level="warning")` or
`PyvergeBroker(..., health_fail_level=...)` raises earlier. If you bind before
all models are registered, pass `validate_health=False` and call
`runtime.validate_health()` after registration.

The runtime also forwards migration context and a run ID:

```python
from pyverge.core import MigrationContext

runtime = FastStreamRuntime(
    manager,
    context_factory=lambda msg: MigrationContext.create(
        {"topic": msg.topic, "headers": dict(msg.headers or {})}
    ),
)
```

`converge(..., context=..., run_id=...)` accepts per-call overrides. Subscriber
decoders use `context_for(msg)`; publisher and route bindings use the runtime's
default context.

### Explicit selector

`subscriber(..., selector=...)` accepts a `TargetSelector` and overrides the
default header → topic → default chain. With an explicit selector the adapter
does not rewrite the handler annotation, so annotate the payload for every model
the selector may return.

The explicit decorators below remain available for multiple managers or
existing code. They take a `FastStreamRuntime`; the runtime owns the manager, so
there is no separate `manager=` argument.

### `subscriber(broker, *topics, runtime=..., targets=..., header=...)`

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
    runtime=runtime,
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
@subscriber(broker, "orders.v1", runtime=runtime, header="accept-version")
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

### `publisher(broker, *topics, runtime=..., target=...)`

Registers a FastStream publisher and converges the handler's **return** to
`target` before publish. A handler that returns a bound model is dumped to a
payload and converged; a return without a resolvable `(kind, version)` is logged
and passed through unchanged.

Stacking `@subscriber(...)` over `@publisher(...)` gives an in/out bridge; the
in-target and out-target may differ.

### `publish_to(broker, routes={...}, runtime=...)`

For different targets per destination, `publish_to` converges the handler's
return once per route and publishes separately. The handler returns the model
unchanged; the adapter owns dumping, convergence, and publishing:

```python
@subscriber(broker, "orders.v1", "orders.v2", runtime=runtime)
@publish_to(
    broker,
    routes={
        "orders.legacy": "1.0.0",
        "orders.current": "2.0.0",
    },
    runtime=runtime,
)
async def handle(order: Order) -> Order:
    return order
```

`runtime.dump` runs once; each route then converges independently. The wrapper
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
    runtime=runtime,
    targets="latest",
)
@publish_to(
    broker,
    routes={
        "orders.legacy": "1.0.0",
        "orders.current": "2.0.0",
    },
    runtime=runtime,
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
