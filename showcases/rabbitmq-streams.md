# RabbitMQ / Streams Workers

## Problem

A queue or stream carries messages written by older producers. Each message has
a schema version. Workers expect a particular target schema and must not
acknowledge messages they could not process correctly.

## How converge helps

The worker converges each message before handling it and acknowledges only
after the migrated payload is processed. Messages whose migration path is
broken are rejected without requeue, routing them to a dead-letter queue.

## Example flow

1. A producer enqueued `Order` messages at `1.0.0`.
2. A release adds `currency` at `2.0.0`; a migration `1.0.0 → 2.0.0` is
   registered.
3. The worker converges each message to `2.0.0`, then runs business logic.
4. Success → `ack`; migration failure → `reject(requeue=False)`.

## Quick start (projected)

Uses the high-level `ModelManager` facade with a thin adapter around the
`aio-pika` driver. **Illustrative — the transport glue is not shipped.**

```python
import json
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge.migration import MigrationSettings, ModelManager, PydanticModelAdapter

OrderManager = ModelManager.scoped(
    semver.Version,
    adapter=PydanticModelAdapter(),
    settings=MigrationSettings(direction="forward", on_missing_path="raise"),
)


@OrderManager.model()
class OrderV1(BaseModel):
    kind: Literal["Order"] = "Order"
    version: Literal["1.0.0"] = "1.0.0"
    order_id: str
    total: float


@OrderManager.model()
class OrderV2(BaseModel):
    kind: Literal["Order"] = "Order"
    version: Literal["2.0.0"] = "2.0.0"
    order_id: str
    total: float
    currency: str = "USD"


@OrderManager.migration("Order", "1.0.0", "2.0.0")
def add_currency(data: dict) -> dict:
    return {**data, "currency": "USD"}


manager = OrderManager()

# Projected — real driver: aio-pika. Not shipped.
import aio_pika


class StreamWorker:
    """Adapts an AMQP queue to converge messages before handling."""

    def __init__(self, channel, manager, queue_name: str, target="latest"):
        self._channel = channel
        self._manager = manager
        self._queue_name = queue_name
        self._target = target

    async def run(self, handle) -> None:
        queue = await self._channel.declare_queue(self._queue_name)
        async with queue.iterator() as messages:
            async for message in messages:
                try:
                    migrated = self._manager.migrate(
                        json.loads(message.body), target=self._target
                    )
                    await handle(migrated)
                    await message.ack()
                except Exception:  # e.g. MigrationError
                    await message.reject(requeue=False)


async def main():
    worker = StreamWorker(channel, manager, "orders.v1", target="latest")
    await worker.run(process_order)
```

## Abstractions used

- **ModelManager** — high-level facade; `manager.migrate(message, target=...)`
  converges the payload.
- **StreamWorker** — thin adapter owning the ack/reject lifecycle.
- **`on_missing_path="raise"`** — a broken path raises, so the message is
  rejected instead of silently passed along.

## Out of scope

- Requeue/retry policies — broken messages are rejected without requeue; how
  they are retried or inspected is the caller's concern.
- Prefetch and concurrency tuning — the adapter runs sequentially; scale with
  more workers or the level-parallel executor.
