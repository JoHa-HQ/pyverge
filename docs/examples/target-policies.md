# Target policies

This page is executed in CI.

```python
import semver
from pydantic import BaseModel

from pyverge import Manager
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


@UserManager.model()
class UserV3(BaseModel):
    kind: str = "User"
    version: str = "3.0.0"
    name: str
    age: int = 0
    status: str = "active"


@UserManager.migration("User", "1.0.0", "2.0.0", migration_id="docs.targets.v1_v2")
def v1_to_v2(data: dict, context=None) -> dict:
    return {**data, "age": 0}


@UserManager.migration("User", "2.0.0", "3.0.0", migration_id="docs.targets.v2_v3")
def v2_to_v3(data: dict, context=None) -> dict:
    return {**data, "status": "active"}


manager = UserManager()
payload = {"kind": "User", "version": "1.0.0", "name": "Alice"}

assert manager.runner().run(payload, "latest")["version"] == "3.0.0"
assert manager.runner().run(payload, "earliest")["version"] == "1.0.0"
assert manager.runner().run(payload, "2.0.0")["version"] == "2.0.0"
assert manager.runner().run(payload, {"User": "2.0.0"})["version"] == "2.0.0"
assert manager.runner().run(payload, "skip")["version"] == "1.0.0"
```
