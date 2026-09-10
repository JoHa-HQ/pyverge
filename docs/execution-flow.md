# Execution Flow

The library automates the entire flow:

1. **Discover** every versioned entry in the payload (including deeply nested
   ones).
2. **Resolve** the target version for each entry based on the policy.
3. **Plan** the migration path and ordering (children before parents).
4. **Execute** migrations safely with hooks and error handling.
5. **Finalize** each entry against the target schema.

For every discovered entry the engine asks the resolver for a target, then
asks the registry for a migration path. The decision chain looks like this:

```mermaid
flowchart TD
    A[Discover versioned entry] --> B{source == target?}
    B -->|yes| C[No-op]
    B -->|no| D{Path exists in registry?}
    D -->|no| E[Missing path: skip / raise]
    D -->|yes| F{Direction allows migration?}
    F -->|no| G[Direction violation: skip / raise]
    F -->|yes| H[Execute steps in path order]
    H --> I[Finalize data against target model]
    C --> J[Migrated entry]
    E --> J
    G --> J
    I --> J
```

## Concrete example

A payload with two entries at different versions:

```mermaid
flowchart LR
    subgraph Payload
        PU["User 1.0.0"]
        PA["Address 1.0.0"]
    end

    subgraph Resolution
        RU["target: User 3.0.0"]
        RA["target: Address 2.0.0"]
    end

    subgraph Paths
        PU -->|1.0.0 -> 2.0.0| U2["User 2.0.0"]
        U2 -->|2.0.0 -> 3.0.0| RU
        PA -->|1.0.0 -> 2.0.0| RA
    end

    Payload --> Resolution
```

The walker finds both entries. The resolver picks targets. The graph builder
computes paths. The executor runs `Address 1.0.0 -> 2.0.0` first (child), then
`User 1.0.0 -> 2.0.0 -> 3.0.0` (parent).

## Nested model structure

A nested versioned model — Person with Address and Contacts — illustrates how
containment drives discovery and ordering:

```
PersonContainer
└── document: Person (discriminator="version")
    ├── PersonV1 (version="1.0.0")
    │   ├── name: str
    │   └── address: Address
    │       ├── AddressV1 (version="1.0.0"): street, city
    │       └── AddressV2 (version="2.0.0"): +country?, +postal_code?
    │
    └── PersonV2 (version="2.0.0")
        ├── name: str
        ├── address: Address   (same discriminated union)
        ├── contacts: list[Contact]
        │   ├── ContactV1 (version="1.0.0"): phone
        │   └── ContactV2 (version="2.0.0"): +email?, +preferred="phone"
        └── AddressV3 (version="3.0.0"): +region?
```

The walker discovers every versioned entry at any depth. The graph builder
orders them so children migrate before their parents: `Address` and `Contact`
entries converge first, then the enclosing `Person`.

## Migrating a nested payload

A container model drives schema-guided discovery. Register the container and
its versioned models, then migrate a nested payload:

```python
from pyverge.migration import (
    MigrationSettings,
    ModelManager,
    PydanticModelAdapter,
    PydanticWalker,
)

UserManager = ModelManager[semver.Version].scoped(
    PydanticModelAdapter(),
    settings=MigrationSettings(),
    walker=PydanticWalker(
        registry,
        settings=MigrationSettings(),
        adapter=PydanticModelAdapter(),
    ),
)

# Register versioned models (PersonV1, PersonV2, AddressV1, AddressV2, ...)
# and their migrations, then migrate a nested payload:
migrated = manager.migrate(
    {
        "document": {
            "kind": "Person",
            "version": "1.0.0",
            "name": "Alice",
            "address": {"kind": "Address", "version": "1.0.0", "street": "Main"},
        }
    },
    container=PersonContainer,
)
```

The walker discovers `Address 1.0.0` and `Person 1.0.0`, converges the address
first, then the person — so the parent migration never sees stale children.

## Executors

The engine runs the migration graph with an executor. The default is
sequential (topological order, one entry at a time). For throughput on large
payloads, enable level-parallel execution — independent entries within each
topological level run concurrently:

```python
from pyverge.migration import MigrationSettings

UserManager = ModelManager[semver.Version].scoped(
    PydanticModelAdapter(),
    settings=MigrationSettings(parallel_workers=4),
)
```

`parallel_workers` caps the thread pool per execution wave (`0` = sequential,
capped at `os.cpu_count()`). Entries in the same wave are independent, so
parallelism is safe: children always finish before their parents.

You can also inject a custom executor per call:

```python
from pyverge.migration import LevelParallelExecutor

manager.migrate(payload, executor=LevelParallelExecutor(max_workers=4))
```
