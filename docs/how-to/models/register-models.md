# Register models and migrations

## Prerequisites

- A configured `Manager` subclass.
- Model classes or JSON schemas with stable `kind` and `version` values.

## Steps

### Decorator registration

Register models and migrations with decorators at class definition time. Version
and kind are read from the class itself.

```python
from typing import Literal

import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.schemas import ModelCodec, PydanticModelAdapter

UserManager = Manager[semver.Version].configure(
    PydanticModelAdapter(codec=ModelCodec(namespace="", version_property="version", kind_property="kind")),
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
def add_age(data: dict, context=None) -> dict:
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


def add_age(data: dict, context=None) -> dict:
    data["age"] = None
    return data


# Class-level registration (preferred) — no instance needed.
UserManager.model()(UserV1)
UserManager.model()(UserV2)
UserManager.migration("User", "1.0.0", "2.0.0")(add_age)

# Runtime instances copy the graph at construction time.
manager = UserManager()
```

### Runtime instance registration

A runtime instance receives a **copy** of the class engine and registry at
construction time. Registration methods are class methods, so this writes to the
class graph:

```python
manager = UserManager()
manager.store_model(UserV1)  # class graph, not manager.engine
```

Register before instantiating when possible:

```python
UserManager.model()(UserV1)
UserManager.model()(UserV2)
UserManager.migration("User", "1.0.0", "2.0.0")(add_age)
manager = UserManager()
```

For deliberate instance-local registration, target the instance engine:

```python
from pyverge.types import ManagerMigrationKey

manager = UserManager()
manager.store_model(UserV1, engine=manager.engine)
manager.store_model(UserV2, engine=manager.engine)
manager.store_migration(
    ManagerMigrationKey("User", "1.0.0", "2.0.0"),
    add_age,
    engine=manager.engine,
)
```

Use instance-local registration only for isolated runtimes, tests, or dynamic
graphs. Class-level registration remains the default.

## Verify

```python
manager = UserManager()
assert manager.get("User", "1.0.0") is not None
assert manager.get("User", "2.0.0") is not None
```

## Troubleshooting

- Duplicate model registration: use `reconcile_model` or register once.
- Runtime instance missing models: register on the class before instantiating.
- Conflicting class/instance graphs: pass `engine=manager.engine` for instance-local registration.

## See also

- [Managers](../../explanation/managers.md) — bounded-context ownership.
- [Author migrations](../migrations/author-migrations.md) — migration totality and reverse edges.
