# Keys and hydration

Use this guide when discovery or routing knows the graph identity before the
model is available.

## Store a key-only placeholder

```python
from pyverge.registry import Registry
from pyverge.versioning import VersionKey, default_content_hasher

registry = Registry(
    namespace="com.acme.users",
    hasher=default_content_hasher(),
)
key = VersionKey.parse("com.acme.users", "User", "1.0.0")
registry.store(key)

assert registry.has_entry(key)
assert registry.find_model(key) is None
```

Key-only entries record topology without loading a model.

## Hydrate the key

```python
from typing import Literal

from pydantic import BaseModel

from pyverge.schemas import ModelCodec, PydanticModelAdapter


class UserV1(BaseModel):
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
registry.hydrate(adapter.versionable(UserV1))

assert registry.get_model(key).descriptor.ref == adapter.ref(UserV1)
```

`hydrate()` upgrades the placeholder. It does not create a model for an
unregistered key.

## Do not use reconcile for hydration

`reconcile()` is for schema reconciliation between full nodes. A key-only entry
must be hydrated:

```python
# registry.reconcile(adapter.versionable(UserV1))  # does not hydrate a key
registry.hydrate(adapter.versionable(UserV1))
```

## Build the graph

```python
from pyverge.graph import GraphBuilder

graph = GraphBuilder().build(registry)
assert graph.get_model(key) is not None
```

A snapshot may contain key-only entries, but execution planning requires every
selected node and edge to be complete.

## Related

- [Graph model and identity](../../explanation/graph-model.md)
- [Namespaces](../../explanation/namespaces.md)
- [Keys and hydration example](../../examples/keys-and-hydration.md)
MD