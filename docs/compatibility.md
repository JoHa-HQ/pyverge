# Compatibility

A diff describes structural change between two versions. Compatibility is a
domain report over that diff.

## Diff

```python
diff = manager.diff("User", "1.0.0", "2.0.0")
diff.added_fields
diff.removed_fields
diff.modified_fields
diff.render()  # RFC 6902 ops
```

## Compatibility report

`pyverge.reflection.CompatibilityReport` excludes identity fields (`kind`,
`version`) and classifies structural change:

```python
from pyverge.reflection import CompatibilityReport

report = CompatibilityReport.from_diff(
    diff,
    identity_fields=frozenset({"kind", "version"}),
)
report.structural_breaking
report.declared_backward_compatible
report.breaking
```

Breaking when any of these is true and the migration was not declared backward
compatible:

- field removed
- field type changed
- required constraint changed
- required field added

Optional additions and identity-only changes are not breaking.

## CLI

```bash
pyverge compat --manager myapp.models:UserManager
pyverge compat --manager myapp.models:UserManager --fail-on-breaking
```

`--fail-on-breaking` exits `3` when a breaking migration is found. See
[CLI Reference](cli.md#compat).
