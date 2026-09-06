# Common Usage Patterns

The manager exposes a small surface for inspecting, validating, and diffing
registered models.

## Lookup

```python
manager.get("User", "1.0.0")        # the registered versionable
manager.get_latest("User")          # highest registered version for the kind
manager.list_versions("User")        # all registered versions for the kind
manager.list_versions()              # all registered versions across kinds
```

## Validation

```python
manager.validate(data, "User", "1.0.0")   # raises ValidationError on mismatch
```

## Diffing two versions

```python
diff = manager.diff("User", "1.0.0", "2.0.0")
diff.has_additions                  # True if fields were added
diff.added_fields                   # ["age"]
diff.has_removals                   # True if fields were removed
diff.has_modifications              # True if fields changed type/required
diff.render()                       # RFC 6902 JSON Patch ops
```

The diff reports added, removed, and modified fields between two versions of a
kind, and can render the change as an RFC 6902 JSON Patch.

## Migration registration

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

## Hooks

```python
manager.add_hook(("User", "1.0.0", "2.0.0"), MyHook())
```
