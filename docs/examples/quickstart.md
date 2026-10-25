# Executable quickstart

This page is executed in CI.

```python
import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.schemas import PydanticModelAdapter

UserManager = Manager[semver.Version].configure(PydanticModelAdapter())


@UserManager.model()
class UserV1(BaseModel):
    kind: str = "User"
    version: str = "1.0.0"
    name: str


@UserManager.model()
class UserV2(BaseModel):
    kind: str = "User"
    version: str = "2.0.0"
    name: str
    age: int = 0


@UserManager.migration(
    "User",
    "1.0.0",
    "2.0.0",
    migration_id="docs.quickstart.add_age",
)
def add_age(data: dict, context=None) -> dict:
    return {**data, "age": 0}

manager = UserManager()
result = manager.runner().run(
    {"kind": "User", "version": "1.0.0", "name": "Alice"},
    "latest",
)

assert result["version"] == "2.0.0"
assert result["age"] == 0
```
