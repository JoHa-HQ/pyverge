# Document Storage

## Problem

Stored documents persist for months or years. As schemas evolve, older
documents no longer match what readers expect. Rewriting every document on
every schema change is expensive and often impossible while the app is live.

## How converge helps

The read path converges each stored document to the app's target schema before
it is returned. No batch rewrite needed — documents are migrated lazily, on
demand, with per-kind target policies.

## Example flow

1. An app writes `Order` documents at schema `1.0.0`.
2. A release adds `currency` at `2.0.0`; a migration `1.0.0 → 2.0.0` is
   registered.
3. Older documents are still stored at `1.0.0`.
4. On read, the adapter converges them to `2.0.0`; optionally rewrites them
   back so the store self-compacts over time.

## Quick start (projected)

Uses the high-level `ModelManager` facade with a thin adapter around the
`motor` driver. **Illustrative — the transport glue is not shipped.**

```python
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

# Projected — real driver: motor. Not shipped.
from motor.motor_asyncio import AsyncIOMotorCollection


class DocumentStore:
    """Adapts a Mongo collection to converge documents on read."""

    def __init__(self, collection: AsyncIOMotorCollection, manager, target="latest"):
        self._collection = collection
        self._manager = manager
        self._target = target

    async def get(self, doc_id: str) -> dict:
        doc = await self._collection.find_one({"_id": doc_id})
        return self._manager.migrate(doc, target=self._target)

    async def get_and_rewrite(self, doc_id: str) -> dict:
        migrated = await self.get(doc_id)
        await self._collection.replace_one({"_id": doc_id}, migrated)
        return migrated


async def main():
    store = DocumentStore(collection, manager, target={"Order": "latest"})
    doc = await store.get("order_42")
```

## Abstractions used

- **ModelManager** — high-level facade; `manager.migrate(doc, target=...)`
  converges the document.
- **DocumentStore** — thin adapter hiding the migration step from callers.
- **Per-kind target** — `{"Order": "latest"}` pins convergence to the app's
  current schema.

## Out of scope

- Compaction cadence — `get_and_rewrite` is lazy; when to rewrite is the
  caller's decision.
- Documents with no valid migration path — `on_missing_path="raise"` surfaces
  them instead of returning corrupt data; how you repair them is up to you.
