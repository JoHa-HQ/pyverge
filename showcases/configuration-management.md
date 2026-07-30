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
resolver = compile_target_resolver(
    registry,
    {"FeatureFlags": "1.0.0"},
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


class FeatureFlagsV1(BaseModel):
    dark_mode: bool
    version: Literal["1.0.0"] = "1.0.0"


class FeatureFlagsV2(BaseModel):
    dark_mode: bool
    notifications: bool = True
    version: Literal["2.0.0"] = "2.0.0"


engine = Engine(
    registry,
    MigrationSettings(
        version_property="version",
        kind_property="kind",
        direction="any",
        target_strategy="latest",
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

v1 = _version(FeatureFlagsV1, "FeatureFlags", "1.0.0")
v2 = _version(FeatureFlagsV2, "FeatureFlags", "2.0.0")

engine.store_model(v1)
engine.store_model(v2)

engine.store_migration(
    (v1, v2),
    lambda d: {**d, "notifications": True},
)
engine.store_migration(
    (v2, v1),
    lambda d: {k: v for k, v in d.items() if k in {"dark_mode", "version", "kind"}},
)

# Normal load: latest schema.
migrated = engine.migrate(
    {"kind": "FeatureFlags", "version": "1.0.0", "dark_mode": True}
)
assert migrated["version"] == "2.0.0"
assert migrated["notifications"] is True

# Rollback: pin to the earliest schema.
rollback = engine.migrate(
    {"kind": "FeatureFlags", "version": "2.0.0", "dark_mode": True, "notifications": False},
    target_resolver=compile_target_resolver(registry, {"FeatureFlags": "earliest"}),
)
assert rollback["version"] == "1.0.0"
assert "notifications" not in rollback
```

### Abstractions used

- **Engine** with `direction="any"` — supports both forward migration and
  backward rollback.
- **compile_target_resolver** — lets the app pin a specific target schema at
  runtime.
- **SequentialExecutor** — configuration payloads are typically small and
  single-threaded.

## Out of scope

- Persistence — the engine returns a dict; where and how the config is stored is
  the caller's responsibility.
- Validation of unknown keys — use `MigrationSettings.on_extra_field` or handle
  it in migration functions.
