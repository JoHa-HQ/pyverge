# Meta Versions

A version can be registered by its `(kind, version)` pair alone, with no
concrete model. This is useful when a version chain is represented as
declarative patches against a single latest model — for example, git-versioned
JSON specs where only the latest schema is kept and older versions exist only
as patch deltas.

Meta versions behave like any other version:

- **Ordering** — they sort with real versions of the same kind by version value.
- **Discovery** — a payload entry whose `(kind, version)` matches a registered
  meta version is discovered as a migratable entry.
- **Migration** — edges between meta versions (and to a real target) apply in
  order, converging stored payloads to the latest version.
- **Backward migration** — a reverse edge with `from`/`to` swapped and its own
  ops is registered as its own edge; without it, backward migration raises.

Because a meta version has no schema, migration edges touching one produce
**empty diffs** and skip validation/finalization. The engine only validates
against the real target model at the end of the chain.

## Materializing a meta version

A meta version can be materialized into a concrete model automatically. When
`on_missing_model="reconstruct"` is set, registering a migration whose endpoint
has no model reconstructs it from the other endpoint's model and the
migration's diff:

```python
from pyverge.migration import MigrationSettings

UserManager = ModelManager[semver.Version].scoped(
    PydanticModelAdapter(),
    settings=MigrationSettings(on_missing_model="reconstruct"),
)
manager = UserManager()

# Register the real model, then a migration from an unregistered version.
manager.store_model(UserV2)
manager.store_migration(
    ("User", "1.0.0", "2.0.0"),
    JsonPatchMigration(
        {
            "from": "1.0.0",
            "to": "2.0.0",
            "ops": [{"op": "add", "path": "/age", "value": None}],
        }
    ),
)

# The 1.0.0 model is reconstructed from UserV2 minus the added field.
v1 = manager.get("User", "1.0.0")
assert v1.model is not None  # fields: kind, version, name
```

The reconstructed model is stored in the registry in place of the meta node,
so it can be validated against, introspected, or served with a
version-accurate schema. With the default `on_missing_model="raise"`, an
unregistered endpoint raises `ModelNotFoundError`.

## Registering a meta version

```python
import semver
from pydantic import BaseModel

from pyverge.migration import JsonPatchMigration, VersionNode

# Register a meta version: (kind, version) with no model.
meta = VersionNode[semver.Version, BaseModel](
    _model=None,
    _value=semver.Version(0, 1, 0),
    _kind="User",
)
manager.store_model(meta)

# Register a migration from the meta version to a real model.
manager.store_migration(
    (meta, UserV1),
    JsonPatchMigration(
        {
            "from": "0.1.0",
            "to": "1.0.0",
            "ops": [{"op": "replace", "path": "/version", "value": "1.0.0"}],
        }
    ),
)
```

## Backward migration

Backward migration across a meta chain works by registering a reverse edge with
`from`/`to` swapped and its own ops:

```python
# Forward edge: 0.1.0 -> 0.2.0
manager.store_migration((v01, v02), forward_ops)

# Reverse edge: 0.2.0 -> 0.1.0 (swapped spec, own ops)
manager.store_migration((v02, v01), reverse_ops)
```

Without a registered reverse edge, a backward migration raises.
