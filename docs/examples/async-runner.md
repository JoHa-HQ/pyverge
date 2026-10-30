# Async execution

This page is executed in CI.

```python
import asyncio

import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.execution import AsyncBackend
from pyverge.schemas import ModelCodec, PydanticModelAdapter

UserManager = Manager[semver.Version].configure(PydanticModelAdapter(codec=ModelCodec(namespace="", version_property="version", kind_property="kind")))


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


@UserManager.migration("User", "1.0.0", "2.0.0", migration_id="docs.async.v1_v2")
async def add_age(data: dict, context=None) -> dict:
    return {**data, "age": 0}


manager = UserManager()
runner = manager.runner(
    runtime=AsyncBackend(
        backend="asyncio",
        backend_options={},
        max_workers=2,
    )
)
result = asyncio.run(
    runner.run({"kind": "User", "version": "1.0.0", "name": "Alice"}, "latest")
)

assert result["version"] == "2.0.0"
assert result["age"] == 0
```
