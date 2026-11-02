# Fill missing schema pieces

A version graph can be missing either a model or a migration. These two
operations are inverses: reconstruct a model from a migration, or generate a
migration from two models.

## Reconstruct a missing model

This page is executed in CI.

```python
import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.migrations import JsonPatchMigration
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.types import ManagerMigrationKey

UserManager = Manager[semver.Version].configure(
    PydanticModelAdapter(codec=ModelCodec(namespace="default", version_property="version", kind_property="kind")),
    on_missing="reconstruct_model",
)


@UserManager.model()
class UserV2(BaseModel):
    kind: str = "User"
    version: str = "2.0.0"
    name: str
    age: int = 0


UserManager.store_migration(
    ManagerMigrationKey("User", "1.0.0", "2.0.0"),
    JsonPatchMigration(
        {
            "from": "1.0.0",
            "to": "2.0.0",
            "ops": [{"op": "add", "path": "/age", "value": 0}],
        }
    ),
)

manager = UserManager()
v1 = manager.get("User", "1.0.0")

model = manager.engine.adapter.resolve(v1.descriptor.ref)
assert "age" not in model.model_fields
```

## Generate a migration from models

This page is executed in CI.

```python
import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.migrations import JsonPatchMigration
from pyverge.schemas import ModelCodec, PydanticModelAdapter

GeneratedUserManager = Manager[semver.Version].configure(
    PydanticModelAdapter(codec=ModelCodec(namespace="default", version_property="version", kind_property="kind"))
)


@GeneratedUserManager.model()
class GeneratedUserV1(BaseModel):
    kind: str = "User"
    version: str = "1.0.0"
    name: str


@GeneratedUserManager.model()
class GeneratedUserV2(BaseModel):
    kind: str = "User"
    version: str = "2.0.0"
    name: str
    age: int = 0


manager = GeneratedUserManager()
source = manager.get("User", "1.0.0")
target = manager.get("User", "2.0.0")
proposal = manager.engine.propose_migration(source, target)

assert isinstance(proposal, JsonPatchMigration)
assert proposal.spec["from"] == "1.0.0"
assert proposal.spec["to"] == "2.0.0"
assert {"op": "add", "path": "/age", "value": 0} in proposal.spec["ops"]
```
