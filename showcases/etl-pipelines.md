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
3. Both are fed into the same manager; the default `target` is `"latest"`.
4. The manager emits records at `3.0.0` regardless of input version.

## Convergence policy

| Setting | Typical value | Why |
|---------|---------------|-----|
| `direction` | `"forward"` | Extracted data usually moves to the warehouse schema. |
| `target` | `"latest"` (default) | Normalize everything to the newest registered model. |
| `on_missing_path` | `"raise"` | A broken migration should fail the job, not silently pass bad data. |

## Batch migration

ETL jobs often process batches of unrelated records. The manager works on a
single payload, so run it once per record through a shared runner. For a
payload with many nested versioned entries, give the runner a thread backend:

```python
from pyverge.execution import ThreadedBackend

runner = manager.runner(backend=ThreadedBackend(max_workers=4))
runner.run(record, "latest")
```

## Quick start

```python
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.execution import ThreadedBackend
from pyverge.schemas import ModelCodec, PydanticModelAdapter

CustomerManager = Manager[semver.Version].configure(PydanticModelAdapter(codec=ModelCodec()))


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
def add_email(data: dict, context=None) -> dict:
    return {**data, "email": None}


@CustomerManager.migration("Customer", "2.0.0", "3.0.0")
def add_segment(data: dict, context=None) -> dict:
    return {**data, "segment": None}


manager = CustomerManager()
runner = manager.runner(
    direction="forward",
    on_missing_path="raise",
    backend=ThreadedBackend(max_workers=4),
)

records = [
    {"kind": "Customer", "version": "1.0.0", "id": 1, "name": "Alice"},
    {"kind": "Customer", "version": "2.0.0", "id": 2, "name": "Bob", "email": None},
]

# Each record converges to the latest registered version by default.
normalized = [runner.run(record, "latest") for record in records]
for record in normalized:
    assert record["version"] == "3.0.0"
```

### Abstractions used

- **Manager** — configured once and reused per record.
- **Default `target="latest"`** — defaults every entry to the newest registered
  version.
- **`ThreadedBackend`** — parallelizes independent entries within a single
  payload.

## Out of scope

- Source-specific I/O — the manager receives dicts; reading CSV/Parquet/DB rows is
  the caller's responsibility.
- Dead-letter handling — catch migration errors at the sink boundary.
