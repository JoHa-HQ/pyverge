# Use FastStream with pyverge

> Upgrading? The `Reflector(manager)` startup hook is removed. Register models
> and migrations before constructing the runtime manager. See the
> [upgrade guide](../../reference/upgrades.md).

## End-to-end example

```python
import asyncio
from typing import Literal, TypedDict, cast

import semver
from faststream import FastStream
from faststream.kafka import KafkaBroker, TestKafkaBroker
from pydantic import BaseModel

from pyverge import Manager
from pyverge.adapters.faststream import (
    publish_to,
    publisher,
    subscriber,
)
from pyverge.providers import PydanticModelAdapter
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


OrderManager = Manager[semver.Version].configure(PydanticModelAdapter())
OrderManager.store_model(Order)
OrderManager.store_migration(ManagerMigrationKey("Order", "1.0.0", "2.0.0"), add_currency)
OrderManager.store_migration(ManagerMigrationKey("Order", "2.0.0", "1.0.0"), drop_currency)
manager = OrderManager()

broker = KafkaBroker("localhost:9092")


# 3. One handler on multiple topics: consume at `latest`, produce at `1.0.0`.
@subscriber(
    broker,
    "orders.v1",
    "orders.v2",
    manager=manager,
    targets="latest",
)
@publisher(broker, "out-topic", manager=manager, target="1.0.0")
async def handle(order: Order) -> Order:
    return order


app = FastStream(broker)


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
[Migrations → Type the payload shapes](../author-migrations.md#type-the-payload-shapes).

## See also

- [FastStream integration model](../../explanation/faststream.md)
- [FastStream reference](../../reference/faststream.md)
