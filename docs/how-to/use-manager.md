# Use the manager

Task-level examples for graph lookup, validation, diffing, migration
registration, and hooks.

Use the configured manager class for graph operations and a runtime instance
for execution.

## Look up versions

```python
UserManager.get("User", "1.0.0")
UserManager.get_latest_model("User")
UserManager.list_versions("User")
UserManager.list_versions()
UserManager.get_entities()
```

## Validate a payload

Validation is an instance operation:

```python
manager = UserManager()
manager.validate(data, "User", "1.0.0")
```

## Diff two versions

```python
from pyverge.types import ManagerMigrationKey

diff = UserManager.diff(ManagerMigrationKey("User", "1.0.0", "2.0.0"))
diff.has_additions
diff.added_fields
diff.has_removals
diff.has_modifications
```

## Register a migration

Register on the configured class before constructing the runtime instance:

```python
from pyverge.migrations import JsonPatchMigration
from pyverge.types import ManagerMigrationKey

UserManager.store_migration(
    ManagerMigrationKey("User", "1.0.0", "2.0.0"),
    add_age,
)

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
```

## Add hooks

```python
UserManager.add_hook(
    ManagerMigrationKey("User", "1.0.0", "2.0.0"),
    MyHook(),
)
```

Hooks observe migrations before, after, and on error. See
[Telemetry and hooks](telemetry.md).

## See also

- [Register models and migrations](register-models.md)
- [Manager API](../reference/manager.md)
