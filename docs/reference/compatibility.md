# Compatibility

A diff describes structural change between two versions. Compatibility is a
domain report over that diff.

## Diff

```python
from pyverge.types import ManagerMigrationKey

diff = UserManager.diff(ManagerMigrationKey("User", "1.0.0", "2.0.0"))
diff.added_fields
diff.removed_fields
diff.modified_fields
diff.render()  # RFC 6902 ops
```

## Compatibility report

`CompatibilityReport` excludes identity fields (`kind`, `version`) and
classifies structural change:

```python
from pyverge.versioning import CompatibilityReport

report = CompatibilityReport.from_diff(
    diff,
    identity_fields=frozenset({"kind", "version"}),
)
report.structural_breaking
report.removed_fields
report.modified_fields
```

## Guard

`BackwardCompatibilityGuard` evaluates a diff with a fixed identity-field set:

```python
from pyverge.versioning import BackwardCompatibilityGuard

guard = BackwardCompatibilityGuard(frozenset({"kind", "version"}))
guard.evaluate(diff)
guard.required_additions(diff, report)
```

## CLI

Compatibility checks are also available from the CLI:

```bash
pyverge compat --manager myapp.models:UserManager --fail-on-breaking
```

See [CLI reference](cli.md#compat).
