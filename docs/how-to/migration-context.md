# Use runtime context in migrations

A migration can read values that are only known when it runs — tenant ids,
request timestamps, exchange rates. Pass them to `migrate`; the same
`MigrationContext` reaches every step:

```python
result = manager.runner().run(payload, "latest", context={"tenant_id": "tenant_99"})
```

The context is a read-only **view** over the mapping you pass, not a copy.
Creation is O(1) and the same instance reaches every step. Do not mutate the
source mapping while a migration is running.

**JSON Patch does not read context.** RFC 6902 has no variables, and keeping it
free of them is what makes it portable. If an op needs a runtime value, promote
that migration to JSONata (declarative + context) or a callable.

Every runtime callable uses the same contract:

```python
from pyverge.core import ManagerMigrationKey

def migrate_v1_to_v2(data, context=None):
    data["tenant_id"] = context["tenant_id"]
    return data

UserManager.store_migration(
    ManagerMigrationKey("User", "1.0.0", "2.0.0"),
    migrate_v1_to_v2,
)
```

`context` is always provided by the engine; the default `None` keeps direct
calls and tests simple.

## See also

- [Run payloads](run-payloads.md)
- [Author migrations](author-migrations.md)
- [Telemetry and hooks](telemetry.md)
