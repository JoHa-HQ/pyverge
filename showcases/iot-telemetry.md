# IoT Telemetry

## Problem

Devices in the field report sensor readings with firmware-specific schemas.
Older firmware may omit fields that newer dashboards require, or use different
units. Gateways and dashboards need a single, current schema to aggregate and
visualize telemetry.

## How converge helps

Each telemetry payload carries a `device_kind` and `firmware_version`. The
engine migrates incoming payloads to the latest firmware schema before they
reach storage or stream consumers. Per-device-kind policies let some fleets lag
behind intentionally.

## Example flow

1. A temperature sensor reports at firmware `1.0.0`: `{"temp": 22}`.
2. Firmware `2.0.0` adds `humidity` and renames `temp` to `temperature_c`.
3. The engine registers both schemas and a migration `1.0.0 → 2.0.0`.
4. All stored telemetry appears as `2.0.0` records.

## Convergence policy

| Setting | Typical value | Why |
|---------|---------------|-----|
| `direction` | `"forward"` | Devices upgrade firmware; telemetry moves to newer schemas. |
| `target_strategy` | `"latest"` | Dashboards and storage expect the current schema. |
| `on_direction_violation` | `"skip"` | A newer message arriving at an older gateway can be ignored. |

## Per-fleet lag

Some devices cannot be upgraded immediately. A per-kind policy pins those fleets
to an intermediate target while the rest converge to `latest`:

```python
resolver = compile_target_resolver(
    registry,
    {
        "LegacySensor": "1.5.0",
        "*": "latest",
    },
)
```

## Quick start

```python
from typing import Literal

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


class TempSensorV1(BaseModel):
    device_id: str
    temp: float
    version: Literal["1.0.0"] = "1.0.0"


class TempSensorV2(BaseModel):
    device_id: str
    temperature_c: float
    humidity: float | None = None
    version: Literal["2.0.0"] = "2.0.0"


engine = Engine(
    registry,
    MigrationSettings(
        version_property="version",
        kind_property="kind",
        direction="forward",
        on_direction_violation="skip",
    ),
    SequentialExecutor(),
    GraphBuilder(
        registry,
        MigrationSettings(),
        CompoundKeyWalker(registry, settings=MigrationSettings()),
    ),
    adapter,
)

v1 = _version(TempSensorV1, "TempSensor", "1.0.0")
v2 = _version(TempSensorV2, "TempSensor", "2.0.0")

engine.store_model(v1)
engine.store_model(v2)

engine.store_migration(
    (v1, v2),
    lambda d: {
        "device_id": d["device_id"],
        "temperature_c": d["temp"],
        "humidity": None,
    },
)

resolver = compile_target_resolver(registry, "latest")

payload = {"kind": "TempSensor", "version": "1.0.0", "device_id": "abc", "temp": 22.5}
migrated = engine.migrate(payload, target_resolver=resolver)
assert migrated["version"] == "2.0.0"
assert migrated["temperature_c"] == 22.5
```

### Abstractions used

- **Engine** — converges each telemetry payload independently.
- **compile_target_resolver** — lets fleets use different targets.
- **SequentialExecutor** — fine for per-message gateway use; switch to
  `LevelParallelExecutor` for batch ingestion.

## Out of scope

- Time-series compression — the engine only normalizes schema; storage efficiency
  is the database's concern.
- Unit conversion — migrations can change field names and add defaults, but
  numeric conversions belong in explicit migration functions.
