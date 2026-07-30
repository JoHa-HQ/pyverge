# ETL Pipelines

## Problem

Data pipelines read records from many upstream sources — databases, files,
message queues — each with its own schema age. A central warehouse expects a
normalized, latest-schema record. Hand-writing adapters for every source/schema
combination is tedious and error-prone.

## How converge helps

Each record is treated as a versioned payload. The pipeline registers the
models it knows about and the migrations between them, then calls the engine
once per record. Sources stay untouched; the engine produces a uniform output.

## Example flow

1. A CSV extract contains `Customer` records at `1.0.0`.
2. A second source yields `Customer` records already at `2.0.0`.
3. Both are fed into the same engine configured with `target_strategy="latest"`.
4. The engine emits records at `3.0.0` regardless of input version.

## Convergence policy

| Setting | Typical value | Why |
|---------|---------------|-----|
| `direction` | `"forward"` | Extracted data usually moves to the warehouse schema. |
| `target_strategy` | `"latest"` | Normalize everything to the newest registered model. |
| `on_missing_path` | `"raise"` | A broken migration should fail the job, not silently pass bad data. |
| `parallel_workers` | `> 0` | Use `LevelParallelExecutor` for independent records or batches. |

## Batch migration

ETL jobs often process batches of unrelated records. The engine works on a single
payload, but the caller can run many payloads through the same engine instance.
For CPU-bound work, use `LevelParallelExecutor`.

## Quick start

```python
from typing import Literal

import semver
from pydantic import BaseModel

from pydantic_migrator.migration import (
    Engine,
    GraphBuilder,
    LevelParallelExecutor,
    MigrationSettings,
    PydanticModelAdapter,
    Registry,
    VersionNode,
)
from pydantic_migrator.migration.walker import CompoundKeyWalker

adapter = PydanticModelAdapter(version_property="version", kind_property="kind")
registry = Registry[semver.Version]()


def _version(model_cls: type[BaseModel], kind: str, version_str: str) -> VersionNode:
    return VersionNode(model_cls, VersionNode.of(version_str), kind)


class CustomerV1(BaseModel):
    id: int
    name: str
    version: Literal["1.0.0"] = "1.0.0"


class CustomerV2(BaseModel):
    id: int
    name: str
    email: str | None = None
    version: Literal["2.0.0"] = "2.0.0"


class CustomerV3(BaseModel):
    id: int
    name: str
    email: str | None = None
    segment: str | None = None
    version: Literal["3.0.0"] = "3.0.0"


engine = Engine(
    registry,
    MigrationSettings(
        version_property="version",
        kind_property="kind",
        direction="forward",
        target_strategy="latest",
        on_missing_path="raise",
    ),
    LevelParallelExecutor(max_workers=4),
    GraphBuilder(
        registry,
        MigrationSettings(),
        CompoundKeyWalker(registry, settings=MigrationSettings()),
    ),
    adapter,
)

v1 = _version(CustomerV1, "Customer", "1.0.0")
v2 = _version(CustomerV2, "Customer", "2.0.0")
v3 = _version(CustomerV3, "Customer", "3.0.0")

engine.store_model(v1)
engine.store_model(v2)
engine.store_model(v3)

engine.store_migration(
    (v1, v2),
    lambda d: {**d, "email": None},
)
engine.store_migration(
    (v2, v3),
    lambda d: {**d, "segment": None},
)


records = [
    {"kind": "Customer", "version": "1.0.0", "id": 1, "name": "Alice"},
    {"kind": "Customer", "version": "2.0.0", "id": 2, "name": "Bob", "email": None},
]

normalized = [engine.migrate(record) for record in records]
for record in normalized:
    assert record["version"] == "3.0.0"
```

### Abstractions used

- **Engine** — configured once and reused per record.
- **LevelParallelExecutor** — parallelizes independent top-level records within
  a batch.
- **MigrationSettings.target_strategy** — defaults every entry to the latest
  registered version.

## Out of scope

- Source-specific I/O — the engine receives dicts; reading CSV/Parquet/DB rows is
  the caller's responsibility.
- Dead-letter handling — decide what to do with `MigrationError` in your sink.
