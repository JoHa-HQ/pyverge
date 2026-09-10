# Getting Started

## Installation

```bash
# Core library
pip install git+https://github.com/JoHa-HQ/pyverge.git

# With CLI
pip install "git+https://github.com/JoHa-HQ/pyverge.git#egg=pyverge[cli]"
```

The engine is provider-agnostic and works on plain dicts. The examples below
use the shipped Pydantic adapter; a JSON Schema adapter is also available, and
adapters for other model libraries plug in the same way.

## Minimal example

```python
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge.migration import (
    MigrationSettings,
    ModelManager,
    PydanticModelAdapter,
)

# A manager binds a version strategy to an adapter and settings.
UserManager = ModelManager[semver.Version].scoped(
    PydanticModelAdapter(),
    settings=MigrationSettings(),
)


# Register versioned models. Version and kind are read from the class itself.
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


# Register a migration between two versions.
@UserManager.migration("User", "1.0.0", "2.0.0")
def add_age(data: dict) -> dict:
    return {**data, "age": None}


manager = UserManager()

# Migrate data — converges every versioned entry to the configured target.
migrated = manager.migrate(
    {"kind": "User", "version": "1.0.0", "name": "Alice", "email": "a@b.com"}
)
```

`migrate()` converges the payload to the configured target policy (by default
`latest`, the most recently registered version of each kind).

## JSON Schema models

Models can also be defined as JSON Schema documents. The adapter materializes
each schema into a Pydantic model at registration time, so the engine sees the
same `ModelAdapter` contract:

```python
from pyverge.migration import (
    JsonSchemaModelAdapter,
    MigrationSettings,
    ModelManager,
)

UserManager = ModelManager[semver.Version].scoped(
    JsonSchemaModelAdapter(),
    settings=MigrationSettings(),
)

user_schema = {
    "kind": "User",
    "version": "1.0.0",
    "type": "object",
    "properties": {
        "kind": {"type": "string", "default": "User"},
        "version": {"type": "string", "default": "1.0.0"},
        "name": {"type": "string"},
    },
}

UserManager.model()(UserManager.adapter.to_pydantic(user_schema))
```

## Declarative migrations

A migration can be expressed as an RFC 6902 JSON Patch op list instead of a
Python callable. `JsonPatchMigration` compiles the spec into an executable
`JsonPatch` (a `MigrationFunc`):

```python
from pyverge.migration import JsonPatchMigration

migration = JsonPatchMigration(
    {
        "from": "1.0.0",
        "to": "2.0.0",
        "ops": [{"op": "add", "path": "/age", "value": None}],
    }
)
manager.store_migration(("User", "1.0.0", "2.0.0"), migration)
```

The manager unwraps the compiled patch automatically. Core ops (`add`,
`remove`, `replace`, `move`, `copy`, `test`) follow RFC 6902; extended ops
(`set_default`, `coerce`, `map`, `split`) are schema-aware conveniences.

## Next steps

- [Registration](registration.md) — decorator vs. lazy registration, class-level vs. instance-level.
- [Common usage patterns](diffing.md) — lookup, validation, diffing, hooks.
- [Meta versions](meta-versions.md) — version chains without concrete models.
- [Target policy](target-policy.md) — declarative convergence rules.
- [Execution flow](execution-flow.md) — how the engine discovers, plans, and runs migrations.
- [Concepts](concepts.md) — the problem and the approach.
- [Showcases](../showcases/README.md) — end-to-end examples.
