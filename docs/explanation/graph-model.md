# Graph model and identity

pyverge separates graph identity from model payloads. A node is a namespace, a
kind, and a parsed version. An edge connects two nodes in the same namespace.

## Identity objects

`NodeId` is the graph identity:

```python
from pyverge.versioning import NodeId

node = NodeId.parse("com.acme.users", "User", "1.0.0")
assert str(node) == "com.acme.users:User@1.0.0"
```

`VersionKey` adds identity-neutral storage metadata:

```python
from pyverge.versioning import VersionKey

key = VersionKey.parse("com.acme.users", "User", "1.0.0")
```

The `ref` field is preserved but excluded from equality, hashing, ordering, and
digests.

`EdgeKey` is a directed pair of node identities:

```python
from pyverge.versioning import EdgeKey

edge = EdgeKey.from_pair(
    NodeId.parse("com.acme.users", "User", "1.0.0"),
    NodeId.parse("com.acme.users", "User", "2.0.0"),
)
```

Cross-namespace and cross-kind edges are rejected.

## Nodes and edges

`VersionNode` is a hydrated node: it binds a model descriptor and `ModelRef`.
`VersionEdge` is an executable edge: it binds a diff and migration callable.

```text
VersionKey   identity + storage metadata
VersionNode  VersionKey + model descriptor
EdgeKey      source NodeId + target NodeId
VersionEdge  EdgeKey + diff + executable migration
```

Graph snapshots contain identity and serializable migration metadata. They never
contain Python callables.

## Key-only and hydrated entries

A registry entry may be key-only or hydrated:

| Entry | Meaning |
| --- | --- |
| `VersionKey` | topology placeholder, no model |
| `VersionNode` | hydrated model and schema |
| `EdgeKey` | edge identity, no executable binding |
| `VersionEdge` | executable migration binding |

Key-only entries are valid graph content. They let discovery and routing record
topology before models are loaded.

```python
registry.store(key)          # key-only placeholder
registry.hydrate(node)       # upgrade with a full node
```

Hydration and reconciliation are different operations:

- `hydrate` upgrades a key placeholder to a full node;
- `reconcile` resolves schema differences between full nodes.

## Snapshots and paths

`GraphBuilder` compiles registry storage into an immutable `MigrationGraph`:

```python
from pyverge.graph import GraphBuilder

graph = GraphBuilder().build(registry)
```

`PathFinder` compiles target policy, resolves graph paths, applies policy, and
returns a `PathPlan`. Execution planning requires the complete selected path:

- every node on the path hydrated;
- every edge on the path has an executable binding.

A key-only node or unbound edge forbids execution and raises without mutating
the registry.

## Related

- [Namespaces and hydration](namespaces.md)
- [Execution flow](execution-flow.md)
- [Graph reference](../reference/graph.md)
