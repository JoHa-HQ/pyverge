# Migrations

## Basic Migration

Register a migration function between two versions:

```python
@manager.migration("User", "1.0.0", "2.0.0")
def add_age_field(data: dict) -> dict:
    return {**data, "age": None}
```

Migration functions receive a `dict` and return a `dict`. The manager handles validation and model instantiation.

## Multi-step Migration

Migrations chain automatically. If you have `1.0.0 → 2.0.0 → 3.0.0`, calling `migrate(..., "1.0.0", "3.0.0")` executes both steps.

## Batch Migration

```python
# Regular batch
results = manager.migrate_batch(data_list, "User", "1.0.0", "3.0.0")

# Streaming (for large datasets)
for result in manager.migrate_batch_streaming(data_list, "User", "1.0.0", "3.0.0"):
    process(result)
```

## Migration Hooks

Inject custom behavior for logging, metrics, or auditing:

```python
from pydantic_migrator import MigrationHook, MetricsHook

class LoggingHook(MigrationHook):
    def before_migrate(self, name, from_version, to_version, data):
        logger.info(f"Migrating {name} from {from_version} to {to_version}")

    def after_migrate(self, name, from_version, to_version, original, migrated):
        logger.info(f"Successfully migrated {name}")

manager.add_hook(LoggingHook())

# Built-in metrics
metrics = MetricsHook()
manager.add_hook(metrics)
print(f"Success rate: {metrics.success_rate:.1%}")
```

## Migration Testing

```python
from pydantic_migrator import MigrationTestCase

test_cases = [
    MigrationTestCase(
        source={"name": "Alice", "email": "alice@example.com"},
        description="v1→v2 migration adds age",
    )
]
results = manager.test_migration("User", "1.0.0", "2.0.0", test_cases)
results.assert_all_passed()
```

## Model Diff

Compare two versions to see what changed:

```python
diff = manager.diff("User", "1.0.0", "2.0.0")
print(diff.to_markdown())  # Human-readable
print(diff.to_dict())      # JSON-serializable
```
