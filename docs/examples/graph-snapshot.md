# Graph snapshots

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


class DocUserV2(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["2.0.0"] = "2.0.0"
    name: str
    age: int | None = None


class DocUserV3(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["3.0.0"] = "3.0.0"
    name: str


adapter = PydanticModelAdapter(
    codec=ModelCodec(
        namespace="",
        version_property="version",
        kind_property="kind",
    )
)
registry = Registry(namespace="", hasher=default_content_hasher())
source = adapter.versionable(DocUserV1)
target = adapter.versionable(DocUserV2)
key_only = VersionKey.parse("", "User", "3.0.0")

registry.store(source)
registry.store(target)
registry.store(key_only)

before = GraphBuilder().build(registry)
assert before.versions == [source, target]
assert before.has_entry(key_only)
assert before.find_model(key_only) is None

registry.hydrate(adapter.versionable(DocUserV3))
after = GraphBuilder().build(registry)

assert len(before.versions) == 2
assert len(after.versions) == 3
```
MD