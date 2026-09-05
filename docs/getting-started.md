# Getting Started

## Installation

```bash
# Core library
pip install git+https://github.com/JoHa-HQ/pyverge.git

# With CLI
pip install "git+https://github.com/JoHa-HQ/pyverge.git#egg=pyverge[cli]"
```

The engine is provider-agnostic and works on plain dicts. The examples below
use the shipped Pydantic adapter; adapters for other model libraries plug in
the same way.

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

## Next steps

- [Registration](registration.md) — decorator vs. lazy registration, class-level vs. instance-level.
- [Inspecting and diffing](diffing.md) — lookup helpers and version diffs.
- [Meta versions](meta-versions.md) — version chains without concrete models.
- [Target policy](target-policy.md) — declarative convergence rules.
- [Execution flow](execution-flow.md) — how the engine discovers, plans, and runs migrations.
- [Concepts](concepts.md) — the problem and the approach.
- [Showcases](../showcases/README.md) — end-to-end examples.
