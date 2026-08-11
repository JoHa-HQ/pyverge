# IoT Telemetry

## Problem

Devices in the field report sensor readings with firmware-specific schemas.
Older firmware may omit fields that newer dashboards require, or use different
units. Gateways and dashboards need a single, current schema to aggregate and
visualize telemetry.

## How converge helps

Each telemetry payload carries a `kind` and `version` (firmware). The manager
migrates incoming payloads to the latest firmware schema before they reach
storage or stream consumers. Per-kind policies let some fleets lag behind
intentionally.

## Example flow

1. A temperature sensor reports at firmware `1.0.0`: `{"temp": 22}`.
2. Firmware `2.0.0` adds `humidity` and renames `temp` to `temperature_c`.
3. The manager registers both schemas and a migration `1.0.0 → 2.0.0`.
4. All stored telemetry appears as `2.0.0` records.

## Convergence policy

| Setting | Typical value | Why |
|---------|---------------|-----|
| `direction` | `"forward"` | Devices upgrade firmware; telemetry moves to newer schemas. |
| `target` | `"latest"` (default) | Dashboards and storage expect the current schema. |
| `on_direction_violation` | `"skip"` | A newer message arriving at an older gateway can be ignored. |

## Per-fleet lag

Some devices cannot be upgraded immediately. A per-kind target policy pins those
fleets to an intermediate version while the rest converge to `latest`:

```python
manager.migrate(
    payload,
    target={"LegacySensor": "1.5.0", "*": "latest"},
)
```

Pinned kinds must be registered with the manager.

## Quick start

```python
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge.migration import MigrationSettings, ModelManager, PydanticModelAdapter

TempSensorManager = ModelManager[semver.Version].scoped(
    PydanticModelAdapter(),
    settings=MigrationSettings(
        direction="forward",
        on_direction_violation="skip",
    ),
)


@TempSensorManager.model()
class TempSensorV1(BaseModel):
    kind: Literal["TempSensor"] = "TempSensor"
    version: Literal["1.0.0"] = "1.0.0"
    device_id: str
    temp: float


@TempSensorManager.model()
class TempSensorV2(BaseModel):
    kind: Literal["TempSensor"] = "TempSensor"
    version: Literal["2.0.0"] = "2.0.0"
    device_id: str
    temperature_c: float
    humidity: float | None = None


@TempSensorManager.migration("TempSensor", "1.0.0", "2.0.0")
def rename_temp(data: dict) -> dict:
    return {
        "device_id": data["device_id"],
        "temperature_c": data["temp"],
        "humidity": None,
    }


manager = TempSensorManager()

payload = {"kind": "TempSensor", "version": "1.0.0", "device_id": "abc", "temp": 22.5}
migrated = manager.migrate(payload)
assert migrated["version"] == "2.0.0"
assert migrated["temperature_c"] == 22.5
```

### Abstractions used

- **ModelManager** — converges each telemetry payload independently.
- **`target` policy** — per-kind targets let fleets use different schemas.
- **`on_direction_violation="skip"`** — newer messages arriving at an older
  gateway are left as-is instead of failing.

## Out of scope

- Time-series compression — the engine only normalizes schema; storage efficiency
  is the database's concern.
- Unit conversion — migrations can change field names and add defaults, but
  numeric conversions belong in explicit migration functions.
