# Reconstruct missing migrations

The inverse case: you have both concrete models but no migration between them.
Diff the two schemas and render the result as a declarative RFC 6902 spec:

```python
# Both models must be registered (and carry concrete models).
user_v1 = manager.get("User", "1.0.0")
user_v2 = manager.get("User", "2.0.0")

# Diff the two schema versions into a declarative proposal.
proposal = manager.engine.propose_migration(user_v1, user_v2)

# The proposal is a JsonPatchMigration — review it before registering.
UserManager.store_migration(
    ManagerMigrationKey("User", "1.0.0", "2.0.0"), proposal
)
```

The proposal is a **shape-based** diff: it captures field additions, removals
and type changes, but cannot infer business intent (renames, value remaps).
Treat it as a template to edit, never as auto-registered truth.

Unlike model reconstruction, `propose_migration` **never auto-registers** and
**never touches endpoint models** — it returns a proposal you review and
register deliberately.

## See also

- [Reconstruct missing models](reconstruct-missing-models.md)
- [Migration strategies](../explanation/migrations.md)
- [Migration format reference](../reference/migration-formats.md)
