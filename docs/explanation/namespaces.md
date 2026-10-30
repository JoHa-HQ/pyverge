# Namespaces and hydration

A namespace is part of identity, not metadata attached after registration. It
answers the question: *which world does this `User@1.0.0` belong to?*

## One graph, one namespace

A `MigrationGraph` snapshot is single-namespace:

- nodes and edges must share one namespace;
- cross-namespace edges are rejected by `EdgeKey`;
- JGF and manifest IDs render as `namespace:kind@version`.

The empty namespace is valid and is the default for a single application.

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

The manager derives its registry namespace from that codec. There is no separate
manager namespace setting.

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

An empty reference namespace resolves against the owning registry namespace.
An explicit foreign namespace remains unresolved unless that identity exists in
the same registry. Cross-namespace edges are never allowed.

## Related

- [Graph model and identity](graph-model.md)
- [Keys and hydration](../how-to/models/keys-and-hydration.md)
- [Upgrade guide](../reference/upgrades.md)
