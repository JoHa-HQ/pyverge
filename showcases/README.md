# Event Sourcing

## Problem

An event-sourced system replays events written months or years ago. Each event
has a schema version. Consumers expect events at a particular target schema.
Writing per-version upcasters by hand becomes unmanageable.

## How converge helps

The engine treats every event as a self-describing payload. The developer writes
small migration functions between adjacent versions; the engine composes the
full path and applies it atomically per event. This is exactly the “upcaster”
pattern from event-sourcing literature.

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
versions. Each consumer builds its own `TargetResolver` and passes it to the
shared engine through `migrate(..., target_resolver=...)`.

## All-or-nothing per entry

A single event must converge completely or fail completely. Nested sub-events
inside the same payload are independent entries, but each one is also migrated
atomically.

## Quick start

```python
from typing import Any, Literal

import semver
from pydantic import BaseModel

from pydantic_migrator.migration import (
    Engine,
    GraphBuilder,
    MigrationSettings,
    PydanticModelAdapter,
    Registry,
    SequentialExecutor,
    VersionNode,
    compile_target_resolver,
)
from pydantic_migrator.migration.walker import CompoundKeyWalker

adapter = PydanticModelAdapter(version_property="version", kind_property="kind")
registry = Registry[semver.Version]()


def _version(model_cls: type[BaseModel], kind: str, version_str: str) -> VersionNode:
    return VersionNode(model_cls, VersionNode.of(version_str), kind)


class OrderV1(BaseModel):
    order_id: str
    total: float
    version: Literal["1.0.0"] = "1.0.0"


class OrderV2(BaseModel):
    order_id: str
    total: float
    currency: str = "USD"
    version: Literal["2.0.0"] = "2.0.0"


class OrderV3(BaseModel):
    order_id: str
    total: float
    currency: str = "USD"
    items: list[dict[str, Any]] = []
    version: Literal["3.0.0"] = "3.0.0"


engine = Engine(
    registry,
    MigrationSettings(
        version_property="version",
        kind_property="kind",
        direction="forward",
        on_missing_path="raise",
        on_direction_violation="raise",
    ),
    SequentialExecutor(),
    GraphBuilder(
        registry,
        MigrationSettings(),
        CompoundKeyWalker(registry, settings=MigrationSettings()),
    ),
    adapter,
)

v1 = _version(OrderV1, "Order", "1.0.0")
v2 = _version(OrderV2, "Order", "2.0.0")
v3 = _version(OrderV3, "Order", "3.0.0")

engine.store_model(v1)
engine.store_model(v2)
engine.store_model(v3)

engine.store_migration(
    (v1, v2),
    lambda d: {**d, "currency": "USD"},
)
engine.store_migration(
    (v2, v3),
    lambda d: {**d, "items": []},
)


class OrderConsumer:
    def __init__(self, engine: Engine[semver.Version], target_version: str) -> None:
        self.engine = engine
        self.target_version = target_version

    def handle(self, event: dict) -> dict:
        resolver = compile_target_resolver(
            self.engine.registry,
            {"Order": self.target_version},
        )
        return self.engine.migrate(event, target_resolver=resolver)


consumer = OrderConsumer(engine, "3.0.0")
migrated = consumer.handle(
    {"kind": "Order", "version": "1.0.0", "order_id": "42", "total": 9.99}
)
assert migrated["version"] == "3.0.0"
assert migrated["currency"] == "USD"
assert migrated["items"] == []
```

### Abstractions used

- **Engine** — owns the registry, builds the graph, and executes migrations.
- **Registry** — stores versions and explicit migration edges.
- **VersionNode** — binds a model class, kind, and parsed version value.
- **compile_target_resolver** — turns a declarative target policy into a
  per-entry resolver.
- **SequentialExecutor** — runs entries one at a time in topological order.

## Out of scope

- Ordering guarantees — the engine assumes the caller passes events in the
  right order.
- Projection rebuild optimization — the engine migrates one payload at a time.
