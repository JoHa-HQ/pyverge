# Getting started

pyverge is a runtime schema-evolution engine that lets independently deployed producers and consumers exchange versioned payloads without requiring synchronized releases.

> Upgrading from an earlier API? See the
> [upgrade guide](../reference/upgrades.md) for `manager.migrate`,
> `MigrationSettings`, runner, and import-path replacements.

## What you will build

A minimal manager with two model versions, one migration, and a converged payload.

## Prerequisites

Python 3.11 or newer.

```bash
# Core library
pip install pyverge

# With CLI
pip install "pyverge[cli]"
```

The engine is provider-agnostic and works on plain dicts. The examples below
use the shipped Pydantic adapter; a JSON Schema adapter is also available, and
adapters for other model libraries plug in the same way.

## Steps

```python
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.schemas import ModelCodec, PydanticModelAdapter

# A manager binds a version strategy to an adapter.
UserManager = Manager[semver.Version].configure(
    PydanticModelAdapter(codec=ModelCodec(namespace="", version_property="version", kind_property="kind")),
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
def add_age(data: dict, context=None) -> dict:
    return {**data, "age": None}


manager = UserManager()

# Migrate data — converges every versioned entry to the configured target.
migrated = manager.runner().run(
    {"kind": "User", "version": "1.0.0", "name": "Alice", "email": "a@b.com"},
    "latest",
)
```

`runner.run()` converges the payload to the requested target policy (`latest`
here, the most recently registered version of each kind).

## Verify

```python
assert migrated["version"] == "2.0.0"
assert migrated["age"] is None
```

## See also

- [Graph model and identity](../explanation/graph-model.md)
- [Namespaces and hydration](../explanation/namespaces.md)
- [Upgrade guide](../reference/upgrades.md)
- [Providers and JSON Schema models](../explanation/providers.md)
- [Migration formats](../reference/migration-formats.md)
- [Managers](../explanation/managers.md)
- [Author migrations](../how-to/migrations/author-migrations.md)
- [Showcases](https://github.com/JoHa-HQ/pyverge/tree/main/showcases)
