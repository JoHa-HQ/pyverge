# FastStream Integration

pyverge plugs into [FastStream](https://faststream.airt.ai/) as an adapter: your
subscribers keep declaring FastStream handlers, and pyverge converges each
message body to the policy target before the handler runs — and can converge the
handler's return again on publish.

The adapter lives in `pyverge.adapters.faststream`. pyverge core and its ports
never import FastStream — everything is adapter-local composition over one
`Manager` and one broker.

```bash
pip install "pyverge[faststream]" faststream[kafka]
```

## The model

Nothing new is invented: pyverge converges ordinary payloads, and FastStream
delivers them.

- **Consume seam** — a subscriber registered with `@subscriber(...)` decodes the
  body through a pyverge `decoder`, converging it to the target version. The
  handler's typed parameter names the kind and is bound to the version actually
  served, so validation matches what the handler receives.
- **Produce seam** — a publisher registered with `@publisher(...)` converges the
  handler's return value to an outgoing target before FastStream serializes it.
  The two targets are independent, so a handler can bridge versions across a
  topic boundary.
- **Reflection** — `Reflector` reconciles each subscriber's declared payload
  model into the manager graph at startup, failing fast on a broken graph.

Versioning is pyverge's `(kind, version)` on the payload — the adapter adds no
calling convention of FastStream's own.

## End-to-end example

```python
import asyncio
from typing import Literal, TypedDict, cast

import semver
from faststream import FastStream
from faststream.kafka import KafkaBroker, TestKafkaBroker
from pydantic import BaseModel

from pyverge import Manager
from pyverge.adapters.faststream import Reflector, publisher, subscriber
from pyverge.migration import MigrationSettings, PydanticModelAdapter
from pyverge.types import ManagerMigrationKey


# 1. The anchor model: the newest shape (v2).
class Order(BaseModel):
    kind: Literal["Order"] = "Order"
    version: Literal["2.0.0"] = "2.0.0"
    order_id: str
    total: float = 0.0
    currency: str = "USD"


# 2. Typed payload shapes per version, and the migrations between them.
class OrderData(TypedDict):
    kind: Literal["Order"]
    order_id: str
    total: float


class OrderV1Data(OrderData):
    version: Literal["1.0.0"]


class OrderV2Data(OrderData):
    version: Literal["2.0.0"]
    currency: str


def add_currency(data: OrderV1Data) -> OrderV2Data:
    return {**data, "currency": "USD"}


def drop_currency(data: OrderV2Data) -> OrderV1Data:
    data = dict(data)
    del data["currency"]
    return cast(OrderV1Data, data)


manager = Manager[semver.Version].configure(
    MigrationSettings(), PydanticModelAdapter()
)()
manager.store_model(Order)
manager.store_migration(ManagerMigrationKey("Order", "1.0.0", "2.0.0"), add_currency)
manager.store_migration(ManagerMigrationKey("Order", "2.0.0", "1.0.0"), drop_currency)

broker = KafkaBroker("localhost:9092")


# 3. One handler on multiple topics: consume at `latest`, produce at `1.0.0`.
@subscriber(broker, "orders.v1", "orders.v2", manager=manager, target="latest")
@publisher(broker, "out-topic", manager=manager, target="1.0.0")
async def handle(order: Order) -> Order:
    return order


app = FastStream(broker, on_startup=[Reflector(manager)])


async def main() -> None:
    async with TestKafkaBroker(broker) as br:
        # Either versioned topic reaches the same handler.
        await br.publish(
            {"kind": "Order", "version": "1.0.0", "order_id": "1", "total": 9.9},
            "orders.v1",
        )
    # handle() received the v2 shape (currency filled in) and published a v1
    # payload on `out-topic`.


asyncio.run(main())
```

The `TypedDict`s are a documentation/IDE aid; migrations still receive and return
plain dicts at runtime. See
[Migrations → Type the payload shapes](migration.md#type-the-payload-shapes).

## The seams

Both seams are decorators at the endpoint, with the same keyword shape
(`manager=`, `target=`).

### `subscriber(broker, *topics, manager=..., target=...)`

Registers the endpoint with a convergence `decoder` and binds the handler's typed
payload parameter to the served version. Parsing is FastStream's — a two-parameter
decoder composes with the endpoint's default decoder, so any content type works
and pyverge only converges. Optional `binder=` overrides how the parameter is
bound. A handler may subscribe to **several topics** (`*topics`); each body is
converged independently before it reaches the same handler.

### `publisher(broker, *topics, manager=..., target=...)`

Registers a FastStream publisher and converges the handler's **return** to
`target` before publish. A handler that returns a bound model is dumped to a
payload and converged; a return without a resolvable `(kind, version)` is logged
and passed through unchanged.

Stacking `@subscriber(...)` over `@publisher(...)` gives an in/out bridge; the
in-target and out-target may differ.

## Routing

pyverge converges; it does not choose a transport. Because every payload leaves
convergence with an explicit `(kind, version)`, routing **inside the handler** is
deterministic.

The showcase consumes both versioned input topics with **one handler** and routes
the payload to version-specific destinations, converging once per route. The app
assembly exposes the manager and broker in the FastStream context, so the handler
resolves them with `Context(...)`:

```python
from typing import Annotated, Any

from faststream import Context
from pyverge import Manager


async def handle_order(
    event: dict[str, Any],
    manager: Annotated[Manager, Context("manager")],
    broker: Annotated[Any, Context("broker")],
) -> None:
    data = event.get("data", event)
    await broker.publish(manager.migrate(data, target="1.0.0"), "orders.legacy")
    await broker.publish(manager.migrate(data, target="2.0.0"), "orders.current")
```

Registered once for both input topics:

```python
@subscriber(broker, "orders.v1", "orders.v2", manager=manager, target="latest")
```

The subscriber decoder converges the inbound body to `latest`; the handler then
converges per destination (`1.0.0` and `2.0.0`). FastStream's
`@broker.publisher(topic)` is static, so derived destinations publish through
`broker.publish(...)`.

## Reflection

`Reflector(manager)` reflects each subscriber's declared payload model into the
manager graph and validates it. Wire it as the app's startup hook:

```python
app = FastStream(broker, on_startup=[Reflector(manager)])
```

Subscribers are registered at decoration time, so reflection runs synchronously
before the broker connects. A subscriber whose typed parameter is not a provider
model (e.g. `dict`) is skipped.

## Target policy

`target=` accepts pyverge's target policy: `"latest"` (default), `"earliest"`, a
pinned version, or a per-kind mapping (`{"Order": "1.0.0"}`). The policy is bound
per subscription, so different consumers (and the producer) converge to different
versions.

## Identity and failure behavior

Convergence keys off the payload's own `(kind, version)`.

- **Missing/unknown identity** — logged as a warning; the payload passes through
  unchanged (no raise, no inference).
- **No migration path** — raises, so the message is not silently processed.
- **Unparsable body** — the decoder raises, rather than passing the raw body to
  the handler.

## Telemetry

The adapter carries no tracing library and emits no spans. FastStream's own
[OpenTelemetry](https://faststream.airt.ai/latest/getting-started/integrations/)
middleware opens the consume span; pyverge's per-edge `OTELHook` opens migration
spans **as current**, so each step nests under the consume span:

```python
from faststream.kafka.opentelemetry import KafkaTelemetryMiddleware
from pyverge.adapters.otel import OTELHook

broker.add_middleware(KafkaTelemetryMiddleware(tracer_provider=provider))
manager.attach_hooks((OTELHook(tracer=provider.get_tracer("my-service")),))
```

See [Telemetry & Hooks](telemetry.md) for the per-step `OTELHook`.

## Testing

Drive the adapter through FastStream's in-memory `TestKafkaBroker` — no broker
container. See the worked
[`showcases/faststream`](https://github.com/JoHa-HQ/pyverge/tree/main/showcases/faststream)
project (broker selection across Kafka/RabbitMQ/NATS/Redis, Jaeger + OTLP).

## See also

- [Managers](managers.md) — the bounded-context invariant the adapter relies on.
- [Migrations](migration.md) — reconstructing missing models and migrations.
- [Target Policy](target-policy.md) — `latest`/`earliest`/pinned/per-kind.
- [Telemetry & Hooks](telemetry.md) — per-step spans and call-level tracing.
