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
