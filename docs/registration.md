# Registration

## Decorator registration

Register models and migrations with decorators at class definition time. Version
and kind are read from the class itself.

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

## Lazy registration

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
