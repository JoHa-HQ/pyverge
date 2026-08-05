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
| `target_strategy` | `"latest"` | Default to the app's current schema. |
| `on_direction_violation` | `"raise"` | Rollback policies should be explicit, not silent. |

## Pinning and rollback

When rolling back an app version, pin the config target to the older schema:

```python
manager.migrate(payload, target={"FeatureFlags": "1.0.0"})
```

## Quick start

```python
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge.migration import MigrationSettings, ModelManager, PydanticModelAdapter

FeatureFlagsManager = ModelManager[semver.Version].scoped(
    PydanticModelAdapter(),
    settings=MigrationSettings(
        direction="any",
        on_direction_violation="raise",
    ),
)


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
def add_notifications(data: dict) -> dict:
    return {**data, "notifications": True}


@FeatureFlagsManager.migration("FeatureFlags", "2.0.0", "1.0.0")
def drop_notifications(data: dict) -> dict:
    return {k: v for k, v in data.items() if k in {"kind", "version", "dark_mode"}}


manager = FeatureFlagsManager()

# Normal load: latest schema.
migrated = manager.migrate(
    {"kind": "FeatureFlags", "version": "1.0.0", "dark_mode": True}
)
assert migrated["version"] == "2.0.0"
assert migrated["notifications"] is True

# Rollback: pin to the earliest schema.
rollback = manager.migrate(
    {
        "kind": "FeatureFlags",
        "version": "2.0.0",
        "dark_mode": True,
        "notifications": False,
    },
    target="earliest",
)
assert rollback["version"] == "1.0.0"
assert "notifications" not in rollback
```

### Abstractions used

- **ModelManager** with `direction="any"` — supports both forward migration and
  backward rollback.
- **`target` policy** — `manager.migrate(payload, target=...)` pins a specific
  schema at runtime (`"latest"`, `"earliest"`, or a per-kind dict).
- **Migration functions** — registered both ways (`1.0.0 → 2.0.0` and back).

## Out of scope

- Persistence — the engine returns a dict; where and how the config is stored is
  the caller's responsibility.
- Validation of unknown keys — use `MigrationSettings.on_extra_field` or handle
  it in migration functions.
