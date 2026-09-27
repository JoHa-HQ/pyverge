# Model Reflection

A version chain can be represented as declarative patches against a single
latest model — for example, git-versioned JSON specs where only the latest
schema is kept and older versions exist only as patch deltas. With model
reflection, you never register the older versions by hand: register the anchor
model, enable `on_missing="reconstruct_model"`, and the engine materializes
every missing version when you register its migration.

## How it works

When a migration is registered, the engine checks both endpoints against the
registry:

- A **registered** endpoint (with a concrete model) is used as-is.
- An **unregistered** endpoint is reconstructed from the other endpoint's model
  and the migration's diff, then stored in the registry.

The reconstructed model is a real, concrete model — it can be validated
against, introspected, or served with a version-accurate schema.

## Enabling reflection

```python
from pyverge import Manager
from pyverge.migration import MigrationSettings, PydanticModelAdapter

UserManager = Manager[semver.Version].configure(
    MigrationSettings(on_missing="reconstruct_model"),
    PydanticModelAdapter(),
)
manager = UserManager()
```

With the default `on_missing="raise"`, registering a migration with an
unregistered endpoint raises `ModelNotFoundError`.

## Registering the anchor and migrations

Register only the latest concrete model, then register migrations from the
older versions. The engine reconstructs each missing version automatically:

```python
# Register the anchor model (the latest concrete schema).
manager.store_model(UserV2)

# Register a migration from an unregistered version.
# The engine reconstructs the 1.0.0 model from UserV2 minus the added field.
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

# The 1.0.0 model is now materialized.
v1 = manager.get("User", "1.0.0")
assert v1.model is not None  # fields: kind, version, name
```

## Migration formats

Migrations can be Python callables or declarative RFC 6902 JSON Patch specs.
Both are normalized into a diff by the engine's discovery strategies, so
reflection works the same way regardless of format:

```python
# Python callable
manager.store_migration(("User", "1.0.0", "2.0.0"), add_age)

# Declarative JSON Patch spec
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
```

## Proposing a migration

`on_missing` is a single, **exclusive** strategy — pick one:

| Value | Behavior |
| --- | --- |
| `"reconstruct_model"` | Rebuild the missing endpoint *model* from the anchor and the migration diff, then store the migration. |
| `"reconstruct_migration"` | Reconstruct the missing version-edge *migration* by diffing two schemas into a proposal. Model reconstruction is disabled. |
| `"raise"` (default) | Fail with `ModelNotFoundError`. |
| `"skip"` | Leave the version model-less. |

Model reconstruction works from an existing migration; migration reconstruction
is the inverse — you have both models and want a starting patch:

```python
# Both models must be registered (and carry concrete models).
user_v1 = manager.get("User", "1.0.0")
user_v2 = manager.get("User", "2.0.0")

# Diff the two schema versions into a declarative proposal.
proposal = manager.engine.propose_migration(user_v1, user_v2)

# The proposal is a JsonPatchMigration — review it before registering.
manager.store_migration(("User", "1.0.0", "2.0.0"), proposal)
```

The proposal is a **shape-based** diff: it captures field additions, removals
and type changes, but cannot infer business intent (renames, value remaps).
Treat it as a template to edit, never as auto-registered truth.

## Backward migration

Backward migration across a chain works by registering a reverse edge with
`from`/`to` swapped and its own ops:

```python
# Forward edge: 0.1.0 -> 0.2.0
manager.store_migration(("User", "0.1.0", "0.2.0"), forward_ops)

# Reverse edge: 0.2.0 -> 0.1.0 (swapped spec, own ops)
manager.store_migration(("User", "0.2.0", "0.1.0"), reverse_ops)
```

Without a registered reverse edge, a backward migration raises.
