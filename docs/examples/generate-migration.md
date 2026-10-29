# Generate a migration from models

This page is executed in CI.

```python
import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.migrations import JsonPatchMigration
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


manager = UserManager()
source = manager.get("User", "1.0.0")
target = manager.get("User", "2.0.0")
proposal = manager.engine.propose_migration(source, target)

assert isinstance(proposal, JsonPatchMigration)
assert proposal.spec["from"] == "1.0.0"
assert proposal.spec["to"] == "2.0.0"
assert {"op": "add", "path": "/age", "value": 0} in proposal.spec["ops"]
```
