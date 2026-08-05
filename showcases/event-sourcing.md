# Event Sourcing

## Problem

An event-sourced system replays events written months or years ago. Each event
has a schema version. Consumers expect events at a particular target schema.
Writing per-version upcasters by hand becomes unmanageable.

## How converge helps

Every event is a self-describing payload. The developer writes small migration
functions between adjacent versions; the engine composes the full path and
applies it atomically per event. This is exactly the "upcaster" pattern from
event-sourcing literature.

## Example flow

1. A consumer is configured for `Order` events at version `3.0.0`.
2. It receives an `Order` event at `1.0.0`.
3. The engine resolves `1.0.0 → 2.0.0 → 3.0.0`, runs the registered upcasters,
   and returns the event as a `3.0.0` dict.
4. If any step is missing and the gap is not backward-compatible, the engine
   raises before any partial change is applied.

## Convergence policy

| Setting | Typical value | Why |
|---------|---------------|-----|
| `direction` | `"forward"` | Replay usually moves older events to the current schema. |
| `on_missing_path` | `"raise"` | An un-migratable event breaks replay integrity. |
| `on_direction_violation` | `"raise"` | Consumers define the allowed direction; violations are data errors. |

## Per-consumer / per-topic policies

The same event kind may be consumed by different services at different target
versions. Each consumer holds its own `target` policy and passes it to the
shared manager through `migrate(..., target=...)`.

## All-or-nothing per entry

A single event must converge completely or fail completely. Nested sub-events
inside the same payload are independent entries, but each one is also migrated
atomically.

## Quick start

```python
from typing import Any, Literal

import semver
from pydantic import BaseModel

from pyverge.migration import MigrationSettings, ModelManager, PydanticModelAdapter

OrderManager = ModelManager[semver.Version].scoped(
    PydanticModelAdapter(),
    settings=MigrationSettings(
        direction="forward",
        on_missing_path="raise",
        on_direction_violation="raise",
    ),
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


@OrderManager.model()
class OrderV3(BaseModel):
    kind: Literal["Order"] = "Order"
    version: Literal["3.0.0"] = "3.0.0"
    order_id: str
    total: float
    currency: str = "USD"
    items: list[dict[str, Any]] = []


@OrderManager.migration("Order", "1.0.0", "2.0.0")
def add_currency(data: dict) -> dict:
    return {**data, "currency": "USD"}


@OrderManager.migration("Order", "2.0.0", "3.0.0")
def add_items(data: dict) -> dict:
    return {**data, "items": []}


class OrderConsumer:
    def __init__(self, manager, target_version: str) -> None:
        self._manager = manager
        self._target = {"Order": target_version}

    def handle(self, event: dict) -> dict:
        return self._manager.migrate(event, target=self._target)


consumer = OrderConsumer(OrderManager(), "3.0.0")
migrated = consumer.handle(
    {"kind": "Order", "version": "1.0.0", "order_id": "42", "total": 9.99}
)
assert migrated["version"] == "3.0.0"
assert migrated["currency"] == "USD"
assert migrated["items"] == []
```

### Abstractions used

- **ModelManager** — high-level facade; registers models and migrations with
  decorators, and converges events with `migrate(event, target=...)`.
- **`@OrderManager.model()` / `@OrderManager.migration(...)`** — declarative
  registration at class level.
- **Per-consumer target** — `{"Order": "3.0.0"}` pins a consumer to a specific
  schema without touching the shared manager.

## Out of scope

- Ordering guarantees — the engine assumes the caller passes events in the
  right order.
- Projection rebuild optimization — the engine migrates one payload at a time.
