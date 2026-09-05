# Inspecting and Diffing

The manager exposes lookup and diff helpers.

## Lookup helpers

```python
manager.get("User", "1.0.0")        # the registered versionable
manager.get_latest("User")          # highest registered version for the kind
manager.list_versions("User")        # all registered versions for the kind
```

## Diffing two versions

```python
diff = manager.diff("User", "1.0.0", "2.0.0")
diff.has_additions                  # True if fields were added
diff.added_fields                   # ["age"]
diff.render()                       # RFC 6902 JSON Patch ops
```

The diff reports added, removed, and modified fields between two versions of a
kind, and can render the change as an RFC 6902 JSON Patch.
