# Kafka Consumers

## Problem

A consumer group reads records written months ago. Each record carries a schema
version; consumers expect a particular target schema. Writing per-version
upcasters by hand, per topic, becomes unmanageable.

## How converge helps

Every record is converged before business logic runs. The consumer group stays
on the latest schema regardless of when a record was written, and per-topic
target policies let different groups hold different schemas.

## Example flow

1. A producer wrote `Order` records at `1.0.0`.
2. A release adds `currency` at `2.0.0`; a migration `1.0.0 → 2.0.0` is
   registered.
3. The consumer converges each record to `2.0.0` before handling.
4. Records with a broken migration path are dead-lettered, not silently
   processed.

## Quick start (projected)

Uses the high-level `ModelManager` facade with a thin adapter around the
`confluent-kafka` driver. **Illustrative — the transport glue is not shipped.**

```python
import json
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge.migration import MigrationSettings, ModelManager, PydanticModelAdapter

OrderManager = ModelManager[semver.Version].scoped(
    PydanticModelAdapter(),
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

# Projected — real driver: confluent-kafka. Not shipped.
from confluent_kafka import Consumer, Message


class ConvergingConsumer:
    """Adapts a Kafka consumer to converge records before delivery."""

    def __init__(self, consumer: Consumer, manager, target="latest", on_failed=None):
        self._consumer = consumer
        self._manager = manager
        self._target = target
        self._on_failed = on_failed

    def poll(self, timeout: float = 1.0) -> dict | None:
        msg: Message | None = self._consumer.poll(timeout)
        if msg is None or msg.error():
            return None
        payload = json.loads(msg.value())
        try:
            return self._manager.migrate(payload, target=self._target)
        except Exception as exc:  # e.g. MigrationError
            if self._on_failed is not None:
                self._on_failed(msg, exc)  # -> send to DLQ, log, etc.
            return None


consumer = ConvergingConsumer(
    kafka_consumer,
    manager,
    target={"Order": "latest"},
    on_failed=lambda msg, exc: dlq.send(msg.value(), reason=str(exc)),
)
for record in iter(consumer.poll, None):
    handle(record)  # business logic, offset commit owned by the consumer group
```

## Abstractions used

- **ModelManager** — shared, stateless facade; one instance converges every
  record.
- **ConvergingConsumer** — thin adapter that polls, converges, and routes
  failures.
- **Per-kind target** — `{"Order": "latest"}` lets different groups hold
  different schemas without touching the engine.

## Out of scope

- Offset management — committing offsets after `handle(record)` is the
  consumer group's concern.
- Dead-letter policy — `on_failed` receives the raw message; where it goes
  (DLQ, log, retry) is up to you.
