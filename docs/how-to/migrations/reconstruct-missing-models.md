# Reconstruct missing models

## Prerequisites

- One anchor model.
- One migration for the edge.
- `on_missing="reconstruct_model"`.

## Steps

A version chain can be represented as declarative patches against a single
latest model — for example, git-versioned JSON specs where only the latest
schema is kept and older versions exist only as patch deltas. Register the
anchor model and the migration; the engine materializes the missing endpoint
model from the anchor and the migration diff.

Enable the strategy in settings:

```python
from pyverge import Manager
from pyverge.schemas import PydanticModelAdapter

UserManager = Manager[semver.Version].configure(
    PydanticModelAdapter(),
    on_missing="reconstruct_model",
)
```

Then register only the concrete model you have, plus the migration. The engine
reconstructs every missing version on registration:

```python
# Register the anchor model (the latest concrete schema).
UserManager.store_model(UserV2)

# Register a migration from an unregistered version.
# The engine reconstructs the 1.0.0 model from UserV2 minus the added field.
from pyverge.types import ManagerMigrationKey

UserManager.store_migration(
    ManagerMigrationKey("User", "1.0.0", "2.0.0"),
    JsonPatchMigration(
        {
            "from": "1.0.0",
            "to": "2.0.0",
            "ops": [{"op": "add", "path": "/age", "value": None}],
        }
    ),
)

# Runtime instances copy the graph at construction time.
manager = UserManager()

# The 1.0.0 model is now materialized.
v1 = manager.get("User", "1.0.0")
assert v1.model is not None  # fields: kind, version, name
```

When a migration is registered, the engine checks both endpoints against the
registry:

- A **registered** endpoint (with a concrete model) is used as-is.
- An **unregistered** endpoint is reconstructed from the other endpoint's model
  and the migration's diff, then stored in the registry.

The reconstructed model is a real, concrete model — it can be validated
against, introspected, or served with a version-accurate schema. This strategy
**mutates the registry**.

With the default `on_missing="raise"`, registering a migration with an
unregistered endpoint raises `ModelNotFoundError`.

## Verify

```python
manager = UserManager()
assert manager.get("User", "1.0.0").model is not None
```

## Troubleshooting

- `ModelNotFoundError`: neither endpoint is registered.
- Wrong `on_missing` mode: model reconstruction is disabled.

## See also

- [Reconstruct missing migrations](reconstruct-missing-migrations.md)
- [Migration strategies](../../explanation/migrations.md)
- [Author migrations](author-migrations.md)
