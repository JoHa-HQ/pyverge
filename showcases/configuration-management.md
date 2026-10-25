# Configuration Management

## Problem

Applications store configuration in versioned schemas: feature flags, deployment
manifests, user preferences. Older persisted configs must load correctly after the
app upgrades. Downgrading for rollback also matters.

## How converge helps

Configuration is treated as a versioned payload. The engine can migrate an older
config forward to the running app's schema, or roll a newer config backward when
the app reverts. Target policies per config kind make this explicit.

## Example flow

1. App version `2.0.0` expects `FeatureFlags` at schema `2.0.0`.
2. A user's cached config is at `1.0.0`.
3. The engine migrates `1.0.0 → 2.0.0` on load.
4. For rollback, the app can request `target="earliest"`.

## Convergence policy

| Setting | Typical value | Why |
|---------|---------------|-----|
| `direction` | `"any"` | Configs may need forward migration or backward rollback. |
| `target` | `"latest"` (default) | Default to the app's current schema. |
| `on_direction_violation` | `"raise"` | Rollback policies should be explicit, not silent. |

## Pinning and rollback

When rolling back an app version, pin the config target to the older schema:

```python
runner.run(payload, {"FeatureFlags": "1.0.0"})
```

## Quick start

```python
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.schemas import PydanticModelAdapter

FeatureFlagsManager = Manager[semver.Version].configure(PydanticModelAdapter())


@FeatureFlagsManager.model()
class FeatureFlagsV1(BaseModel):
    kind: Literal["FeatureFlags"] = "FeatureFlags"
    version: Literal["1.0.0"] = "1.0.0"
    dark_mode: bool


@FeatureFlagsManager.model()
class FeatureFlagsV2(BaseModel):
    kind: Literal["FeatureFlags"] = "FeatureFlags"
    version: Literal["2.0.0"] = "2.0.0"
    dark_mode: bool
    notifications: bool = True


@FeatureFlagsManager.migration("FeatureFlags", "1.0.0", "2.0.0")
def add_notifications(data: dict, context=None) -> dict:
    return {**data, "notifications": True}


@FeatureFlagsManager.migration("FeatureFlags", "2.0.0", "1.0.0")
def drop_notifications(data: dict, context=None) -> dict:
    return {k: v for k, v in data.items() if k in {"kind", "version", "dark_mode"}}


manager = FeatureFlagsManager()
runner = manager.runner(direction="any", on_direction_violation="raise")

# Normal load: latest schema.
migrated = runner.run(
    {"kind": "FeatureFlags", "version": "1.0.0", "dark_mode": True}, "latest"
)
assert migrated["version"] == "2.0.0"
assert migrated["notifications"] is True

# Rollback: pin to the earliest schema.
rollback = runner.run(
    {
        "kind": "FeatureFlags",
        "version": "2.0.0",
        "dark_mode": True,
        "notifications": False,
    },
    "earliest",
)
assert rollback["version"] == "1.0.0"
assert "notifications" not in rollback
```

### Abstractions used

- **Runner** with `direction="any"` — supports both forward migration and
  backward rollback.
- **`target` policy** — `runner.run(payload, target)` pins a specific schema at
  runtime (`"latest"`, `"earliest"`, or a per-kind dict).
- **Migration functions** — registered both ways (`1.0.0 → 2.0.0` and back).

## Out of scope

- Persistence — the engine returns a dict; where and how the config is stored is
  the caller's responsibility.
- Validation of unknown keys — handle it in migration functions.
