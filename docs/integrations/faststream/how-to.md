# Use FastStream with pyverge

> Upgrading? The `Reflector(manager)` startup hook is removed. Register models
> and migrations before constructing the runtime manager. See the
> [upgrade guide](../../reference/upgrades.md).

## Prerequisites

- Installed FastStream adapter.
- Registered models and migrations on the manager class.

## Steps

### End-to-end example

```python
import asyncio
from typing import Literal, TypedDict, cast

import semver
from faststream import FastStream
from pydantic import BaseModel

from pyverge import Manager
from pyverge.adapters.faststream import PyvergeBroker
from pyverge.schemas import ModelCodec, PydanticModelAdapter
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


def add_currency(data: OrderV1Data, context=None) -> OrderV2Data:
    return {**data, "currency": "USD"}


def drop_currency(data: OrderV2Data, context=None) -> OrderV1Data:
    data = dict(data)
    del data["currency"]
    return cast(OrderV1Data, data)


OrderManager = Manager[semver.Version].configure(
    PydanticModelAdapter(
        codec=ModelCodec(
            namespace="default", version_property="version", kind_property="kind"
        )
    )
)
OrderManager.store_model(Order)
OrderManager.store_migration(
    ManagerMigrationKey("Order", "1.0.0", "2.0.0"), add_currency
)
OrderManager.store_migration(
    ManagerMigrationKey("Order", "2.0.0", "1.0.0"), drop_currency
)
manager = OrderManager()

# 3. Wrap the broker once. Every decorator shares one manager and runtime.
#    Use any FastStream broker; the showcase wires a concrete transport.
raw_broker = ...
broker = PyvergeBroker(raw_broker, manager=manager)


# 4. One handler on multiple topics: consume at `latest`, produce at `1.0.0`.
@broker.subscriber("orders.v1", "orders.v2", target="latest")
@broker.publisher("out-topic", target="1.0.0")
async def handle(order: Order) -> Order:
    return order


app = FastStream(broker.underlying)


async def main() -> None:
    # Bind the runner once, when the application starts.
    broker.bind(manager.runner())
    # Drive `broker.underlying` with the in-memory test broker for your
    # transport. Either versioned topic reaches the same handler.
    # handle() receives the v2 shape (currency filled in) and publishes a v1
    # payload on `out-topic`.


asyncio.run(main())
```

`PyvergeBroker` owns one runtime, so the runner is built once and every
subscriber/publisher shares it. Build the runner with the host application's
execution environment and bind it during startup (`broker.bind(runner)`);
`converge` raises until a runner is bound. Unknown attributes proxy to the wrapped broker,
so `broker.underlying`, `broker.publishers`, FastStream's test broker, and
`FastStream(broker.underlying)` keep working.

### Explicit decorators

For multiple managers or existing code, use the decorators directly:

```python
from pyverge.adapters.faststream import (
    FastStreamRuntime,
    publisher,
    subscriber,
)

inbound = FastStreamRuntime(inbound_manager, inbound_manager.runner())
outbound = FastStreamRuntime(outbound_manager, outbound_manager.runner())


@subscriber(broker, "orders", runtime=inbound, targets="latest")
@publisher(broker, "orders-out", runtime=outbound, target="1.0.0")
async def handle(order: Order) -> Order:
    return order
```

The `TypedDict`s are a documentation/IDE aid; migrations still receive and return
plain dicts at runtime. See
[Migrations → Type the payload shapes](../../explanation/migrations.md#type-the-payload-shapes).

### Telemetry

The adapter carries no tracing library and emits no spans. FastStream's own
[OpenTelemetry](https://faststream.airt.ai/latest/getting-started/integrations/)
middleware opens the consume span; pyverge's per-edge `OTELHook` opens migration
spans **as current**, so each step nests under the consume span:

```python
from pyverge.execution import OTELHook

# FastStream's transport-specific telemetry middleware carries the consume span.
broker.underlying.add_middleware(telemetry_middleware)
manager.attach_hooks((OTELHook(tracer=provider.get_tracer("my-service")),))
```

See [Telemetry & Hooks](../../how-to/operations/instrument-migrations.md) for the per-step `OTELHook`. Step spans include graph namespace, kind, source/target, and migration strategy/identity when available.

### Testing

Drive the adapter through FastStream's in-memory test broker for your transport —
no broker container. See the worked
[`showcases/faststream`](https://github.com/JoHa-HQ/pyverge/tree/main/showcases/faststream)
project for broker selection and telemetry wiring.

## Verify

Publish through the in-memory test broker and assert the handler received the target shape.

## Troubleshooting

- Handler receives old version: runtime manager copy predates registration.
- Import error: install `pyverge[faststream]`.

## See also

- [FastStream integration model](index.md)
- [FastStream reference](reference.md)
