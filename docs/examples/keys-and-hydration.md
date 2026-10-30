# Keys and hydration

```python
from typing import Literal

from pydantic import BaseModel

from pyverge.graph import GraphBuilder
from pyverge.registry import Registry
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.versioning import VersionKey, default_content_hasher


class DocUserV1(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["1.0.0"] = "1.0.0"
    name: str


adapter = PydanticModelAdapter(
    codec=ModelCodec(
        namespace="com.acme.users",
        version_property="version",
        kind_property="kind",
    )
)
registry = Registry(
    namespace="com.acme.users",
    hasher=default_content_hasher(),
)
key = VersionKey.parse("com.acme.users", "User", "1.0.0")

registry.store(key)
assert registry.find_model(key) is None

node = adapter.versionable(DocUserV1)
registry.hydrate(node)

assert registry.get_model(key) is node
graph = GraphBuilder().build(registry)
assert graph.get_model(key) is node
```
