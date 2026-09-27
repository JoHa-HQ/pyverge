# Managers

A `Manager` is a **bounded context** — one version graph, one registry, one
adapter. This page covers how to register models and migrations, and how the
bounded-context invariant shapes how you organize one or several managers.

## The invariant

> A manager owns one complete version graph: register a kind **and every kind it
> transitively contains** in the same manager.

The unit of ownership is not "a kind" — it is **the whole graph rooted at a
source**. If a payload can reach a kind, that kind must live in the manager that
handles the payload.

## Registration

### Decorator registration

Register models and migrations with decorators at class definition time. Version
and kind are read from the class itself.

```python
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.migration import (
    MigrationSettings,
    PydanticModelAdapter,
)

UserManager = Manager[semver.Version].configure(
    MigrationSettings(),
    PydanticModelAdapter(),
)


@UserManager.model()
class UserV1(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["1.0.0"] = "1.0.0"
    name: str
    email: str


@UserManager.model()
class UserV2(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["2.0.0"] = "2.0.0"
    name: str
    email: str
    age: int | None = None


@UserManager.migration("User", "1.0.0", "2.0.0")
def add_age(data: dict) -> dict:
    return {**data, "age": None}
```

### Lazy registration

Define model classes first and register them later, either at the class level
or on a manager instance. This keeps schema definition separate from runtime
wiring and makes testing easier.

```python
class UserV1(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["1.0.0"] = "1.0.0"
    name: str
    email: str


class UserV2(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["2.0.0"] = "2.0.0"
    name: str
    email: str
    age: int | None = None


def add_age(data: dict) -> dict:
    data["age"] = None
    return data


# Class-level registration (preferred) — no instance needed.
UserManager.model()(UserV1)
UserManager.model()(UserV2)
UserManager.migration("User", "1.0.0", "2.0.0")(add_age)

# Instance-level registration (alternative) — use a separate manager class.
OtherManager = Manager[semver.Version].configure(
    MigrationSettings(),
    PydanticModelAdapter(),
)
manager = OtherManager()
manager.store_model(UserV1)
manager.store_model(UserV2)
manager.store_migration((UserV1, UserV2), add_age)
```

Class-level and instance-level registration are alternatives — an instance shares
its class's registry, so registering the same model through both would raise
`ModelAlreadyRegisteredError`.

### Which manager owns what

A model belongs to the manager that owns its **whole version graph** — the kind
and every kind it transitively contains. The rest of this page explains why.

## Why: three engine mechanics

The engine assumes a single registry end to end. Splitting a graph breaks all
three stages:

1. **Discovery** — the walker resolves nested kinds against *one* registry. A
   kind missing from that registry is invisible: never discovered, never
   migrated.
2. **Ordering** — the dependency graph derives parent/child edges from the
   registry's version list for each kind. A split graph loses the containment
   edge, so execution order is no longer guaranteed (children before parents).
3. **Finalize** — the migrated payload is validated against the target model. A
   nested entry absent from that model is **silently dropped**.

## What "per source" means

Group registrations by the **system whose data converges together** — a service,
an MCP tool server, a tenant track — not by kind, file, or team ownership.

```python
# One bounded context: the Weather service, its own complete graph.
WeatherManager = Manager[semver.Version].configure(
    MigrationSettings(),
    JsonSchemaModelAdapter(),
)

# Everything Weather can reach lives here: the tool kind AND its nested kinds.
manager.store_model(search_weather_v1)
manager.store_model(search_weather_v2)
manager.store_model(location_v1)   # nested inside search_weather
manager.store_model(location_v2)
manager.store_migration(("search_weather", "1.0.0", "2.0.0"), ...)
manager.store_migration(("location", "1.0.0", "2.0.0"), ...)
```

The same rule applies to decorator registration: every `@Manager.model()` for a
graph belongs to the same manager class.

## Failure modes

Splitting a graph across managers does not raise — it produces **partial or
lossy** migrations:

```python
# location lives in A, user lives in B, but a user payload embeds a location.
A.migrate(user_payload)   # location converges; parent user left at 1.0.0
B.migrate(user_payload)   # user converges; nested location silently dropped
```

| Symptom | Cause |
| --- | --- |
| Nested entries never migrate | kind not in the handling manager's registry |
| Parent migrated but children stale | missing containment edge -> wrong order |
| Fields vanish after migration | nested entry not in the target model -> dropped at finalize |


## See also

- [Getting Started](getting-started.md) — a minimal end-to-end example.
- [Migrations](migration.md) — reconstruct missing models or migrations.
- [Execution Flow](execution-flow.md) — discovery, ordering, and finalize.
