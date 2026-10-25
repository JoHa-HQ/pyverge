# Author migrations

## Prerequisites

- Registered source and target models.
- An adjacent version edge.
- A JSON Patch, JSONata, or Python callable migration.

## Steps

See [migration authoring rules](../../explanation/migration-authoring.md) for totality, typed payloads, and property-based guards.

### Add backward migration

Backward migration across a chain works by registering a reverse edge with
`from`/`to` swapped and its own ops:

```python
# Forward edge: 0.1.0 -> 0.2.0
UserManager.store_migration(
    ManagerMigrationKey("User", "0.1.0", "0.2.0"), forward_ops
)

# Reverse edge: 0.2.0 -> 0.1.0 (swapped spec, own ops)
UserManager.store_migration(
    ManagerMigrationKey("User", "0.2.0", "0.1.0"), reverse_ops
)
```

Without a registered reverse edge, a backward migration raises.

## Verify

Run the edge and validate the result against the target model:

```python
manager.runner().run(payload, "2.0.0")
```

## Troubleshooting

- `ValidationError` from the target model means the migration is not total.
- Missing reverse path means no backward migration is registered.

## See also

- [Reconstruct missing models](reconstruct-missing-models.md)
- [Migration strategies](../../explanation/migrations.md)
- [Migration format reference](../../reference/migration-formats.md)
