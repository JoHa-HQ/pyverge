# JGF API

This page is executed in CI.

```python
import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.export import ManifestDiff
from pyverge.jgf import JgfExporter
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.versioning import default_content_hasher

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


@UserManager.migration("User", "1.0.0", "2.0.0", migration_id="docs.jgf.v1_v2")
def add_age(data: dict, context=None) -> dict:
    return {**data, "age": 0}


manager = UserManager()
exporter = JgfExporter(default_content_hasher())
document = exporter.export_graph(manager.registry).to_dict()

assert "graph" in document
assert document["graph"]["nodes"]
assert document["graph"]["edges"]
assert exporter.content_hash(manager.registry)

baseline = exporter.export_graph(manager.registry).to_dict()
current = exporter.export_graph(manager.registry).to_dict()
diff = ManifestDiff.compare(baseline, current)
assert not diff.changed
```
