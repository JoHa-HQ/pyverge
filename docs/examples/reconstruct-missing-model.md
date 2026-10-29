# Reconstruct a missing model

This page is executed in CI.

```python
import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.migrations import JsonPatchMigration
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.types import ManagerMigrationKey

UserManager = Manager[semver.Version].configure(
    PydanticModelAdapter(codec=ModelCodec(namespace="", version_property="version", kind_property="kind")),
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
