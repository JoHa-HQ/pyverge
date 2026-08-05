# Getting Started

## Installation

```bash
# Core library
pip install pyverge

# With CLI
pip install "pyverge[cli]"
```

The engine is provider-agnostic and works on plain dicts. The examples below
use the shipped Pydantic adapter; adapters for other model libraries plug in
the same way.

## Quick Start

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

## Registration Patterns

### Lazy registration

Define model classes first and register them later, either at the class level
or on a manager instance. This keeps schema definition separate from runtime
wiring and makes testing easier.

```python
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge.migration import (
    MigrationSettings,
    ModelManager,
    PydanticModelAdapter,
)

UserManager = ModelManager[semver.Version].scoped(
    PydanticModelAdapter(),
    settings=MigrationSettings(),
)


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
OtherManager = ModelManager[semver.Version].scoped(
    PydanticModelAdapter(),
    settings=MigrationSettings(),
)
manager = OtherManager()
manager.store_model(UserV1)
manager.store_model(UserV2)
manager.store_migration((UserV1, UserV2), add_age)
```

Class-level and instance-level registration are alternatives — an instance shares
its class's registry, so registering the same model through both would raise
`ModelAlreadyRegisteredError`.

## Next Steps

- Read the [concepts](concepts.md) page to understand the building blocks.
- See the [showcases](../showcases/README.md) for end-to-end examples.
