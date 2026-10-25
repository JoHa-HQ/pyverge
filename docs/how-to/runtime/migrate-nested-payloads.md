# Migrate nested payloads

## Prerequisites

- Registered container and nested models.
- Migrations for each reachable version edge.

## Steps

A container model drives schema-guided discovery. Register the container and
its versioned models, then migrate a nested payload:

```python
from pyverge import Manager
from pyverge.schemas import PydanticModelAdapter

UserManager = Manager[semver.Version].configure(PydanticModelAdapter())

# Register Person/Address models and migrations on UserManager before
# constructing the runtime instance.
manager = UserManager()

migrated = manager.runner().run(
    {
        "document": {
            "kind": "Person",
            "version": "1.0.0",
            "name": "Alice",
            "address": {"kind": "Address", "version": "1.0.0", "street": "Main"},
        }
    },
    "latest",
    container=PersonContainer,
)
```

The walker discovers `Address 1.0.0` and `Person 1.0.0`, converges the address
first, then the person — so the parent migration never sees stale children.

## Verify

```python
assert migrated["document"]["version"] == "2.0.0"
```

## Troubleshooting

- Nested entries not migrated: child kind is missing from the manager graph.
- Fields disappear: target model omits the nested field.

## See also

- [Execution flow](../../explanation/execution-flow.md)
- [Container and extractor behavior](../../reference/runtime.md)
