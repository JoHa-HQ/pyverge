# OpenLineage hooks

This page is executed in CI.

```python
import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.execution import OpenLineageHook
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


@UserManager.migration(
    "User",
    "1.0.0",
    "2.0.0",
    migration_id="docs.openlineage.v1_v2",
)
def add_age(data: dict, context=None) -> dict:
    return {**data, "age": 0}


class LineageClient:
    def __init__(self) -> None:
        self.events = []

    def emit(self, event) -> None:
        self.events.append(event)


lineage = LineageClient()
UserManager.attach_hooks(
    [
        OpenLineageHook(
            client=lineage,
            namespace="docs",
            producer="docs-example",
        )
    ]
)

manager = UserManager()
result = manager.runner().run(
    {"kind": "User", "version": "1.0.0", "name": "Alice"},
    "latest",
)

assert result["version"] == "2.0.0"
assert [event.eventType.value for event in lineage.events] == ["START", "COMPLETE"]
assert lineage.events[0].job.name == "migration.User"
```
