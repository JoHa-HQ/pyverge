# ETL Pipelines

## Problem

Data pipelines read records from many upstream sources — databases, files,
message queues — each with its own schema age. A central warehouse expects a
normalized, latest-schema record. Hand-writing adapters for every source/schema
combination is tedious and error-prone.

## How converge helps

Each record is treated as a versioned payload. The pipeline registers the
models it knows about and the migrations between them, then calls the manager
once per record. Sources stay untouched; the manager produces a uniform output.

## Example flow

1. A CSV extract contains `Customer` records at `1.0.0`.
2. A second source yields `Customer` records already at `2.0.0`.
3. Both are fed into the same manager configured with `target_strategy="latest"`.
4. The manager emits records at `3.0.0` regardless of input version.

## Convergence policy

| Setting | Typical value | Why |
|---------|---------------|-----|
| `direction` | `"forward"` | Extracted data usually moves to the warehouse schema. |
| `target_strategy` | `"latest"` | Normalize everything to the newest registered model. |
| `on_missing_path` | `"raise"` | A broken migration should fail the job, not silently pass bad data. |

## Batch migration

ETL jobs often process batches of unrelated records. The manager works on a
single payload, so run it once per record through a shared instance. For a
payload with many nested versioned entries, pass an executor per call:

```python
from pyverge.migration import LevelParallelExecutor

manager.migrate(record, executor=LevelParallelExecutor(max_workers=4))
```

## Quick start

```python
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge.migration import MigrationSettings, ModelManager, PydanticModelAdapter

CustomerManager = ModelManager.scoped(
    semver.Version,
    adapter=PydanticModelAdapter(),
    settings=MigrationSettings(
        direction="forward",
        target_strategy="latest",
        on_missing_path="raise",
    ),
)


@CustomerManager.model()
class CustomerV1(BaseModel):
    kind: Literal["Customer"] = "Customer"
    version: Literal["1.0.0"] = "1.0.0"
    id: int
    name: str


@CustomerManager.model()
class CustomerV2(BaseModel):
    kind: Literal["Customer"] = "Customer"
    version: Literal["2.0.0"] = "2.0.0"
    id: int
    name: str
    email: str | None = None


@CustomerManager.model()
class CustomerV3(BaseModel):
    kind: Literal["Customer"] = "Customer"
    version: Literal["3.0.0"] = "3.0.0"
    id: int
    name: str
    email: str | None = None
    segment: str | None = None


@CustomerManager.migration("Customer", "1.0.0", "2.0.0")
def add_email(data: dict) -> dict:
    return {**data, "email": None}


@CustomerManager.migration("Customer", "2.0.0", "3.0.0")
def add_segment(data: dict) -> dict:
    return {**data, "segment": None}


manager = CustomerManager()

records = [
    {"kind": "Customer", "version": "1.0.0", "id": 1, "name": "Alice"},
    {"kind": "Customer", "version": "2.0.0", "id": 2, "name": "Bob", "email": None},
]

# Each record converges to the latest registered version (target_strategy).
normalized = [manager.migrate(record) for record in records]
for record in normalized:
    assert record["version"] == "3.0.0"
```

### Abstractions used

- **ModelManager** — configured once and reused per record.
- **`target_strategy="latest"`** — defaults every entry to the newest registered
  version.
- **`executor=` per call** — `LevelParallelExecutor` parallelizes independent
  entries within a single payload.

## Out of scope

- Source-specific I/O — the manager receives dicts; reading CSV/Parquet/DB rows is
  the caller's responsibility.
- Dead-letter handling — decide what to do with `MigrationError` in your sink.
