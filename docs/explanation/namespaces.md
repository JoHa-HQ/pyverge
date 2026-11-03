# Namespaces and hydration

A namespace is part of identity, not metadata attached after registration. It
answers the question: *which world does this `User@1.0.0` belong to?*

## One graph, one namespace

A `MigrationGraph` snapshot is single-namespace:

- nodes and edges must share one namespace;
- cross-namespace edges are rejected by `EdgeKey`;
- JGF and manifest IDs render as `namespace:kind@version`.

A namespace is always non-empty. `NodeId` rejects an empty namespace. If a
model adapter is configured without one, its codec applies a non-empty default
before identity creation.

## Where the namespace lives

The adapter’s `ModelCodec` is the source of truth:

```python
from pyverge.schemas import ModelCodec, PydanticModelAdapter

adapter = PydanticModelAdapter(
    codec=ModelCodec(
        namespace="com.acme.orders",
        version_property="version",
        kind_property="kind",
    )
)
```

The manager derives and locks its registry namespace from that codec. There is
no separate manager namespace setting.

A registry requires a non-empty namespace. The OSS `Engine` binds exactly one
registry, and its namespace comes from the adapter codec:

```python
from pyverge.core.engine import Engine
from pyverge.core.registry import DEFAULT_HEALTH_LINTERS, Registry
from pyverge.core.versioning import default_content_hasher

registry = Registry(
    namespace="com.acme.orders",
    hasher=default_content_hasher(),
    reflection=reflection,
    linters=DEFAULT_HEALTH_LINTERS,
)

engine = Engine(registry=registry, adapter=adapter)

assert engine.namespace == "com.acme.orders"
```

Multi-namespace composition is intentionally deferred to a separate entity; the
manager and OSS Engine keep one namespace for now.

Adapters use the codec namespace when they create nodes, keys, and references.
That is why the namespace belongs on the codec even when a manager is used.

## Isolation

Two registries can hold the same kind and version in different namespaces:

```text
com.acme.orders:User@1.0.0
com.acme.billing:User@1.0.0
```

They are different identities. A lookup in the orders graph cannot accidentally
resolve the billing node.

## Hydration

Namespace does not change during hydration. Hydration upgrades a key-only
placeholder to a full node with the same identity:

```python
registry.store(key)          # key-only: com.acme.orders:User@1.0.0
registry.hydrate(node)       # full node:  com.acme.orders:User@1.0.0
```

The graph may contain key-only and hydrated entries, but execution planning
requires the selected path to be complete.

## References

Descriptor references are `NodeId` values and therefore carry namespace through:

- canonical serialization;
- missing-reference checks;
- JGF and manifest export.

A reference always carries a non-empty namespace. `NodeId` rejects an empty
reference namespace, so there is no implicit empty-namespace fallback.
An explicit foreign namespace remains unresolved unless that identity exists in
the same registry. Cross-namespace edges are never allowed.

## Related

- [Graph model and identity](graph-model.md)
- [Keys and hydration](../how-to/models/keys-and-hydration.md)
- [Upgrade guide](../reference/upgrades.md)
