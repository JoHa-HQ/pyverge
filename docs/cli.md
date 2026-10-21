# CLI Reference

Install the CLI extra:

```bash
pip install "pyverge[cli]"
```

Commands address a manager as `module:object_path`. The target may be a
manager instance, a configured `Manager` subclass, or a zero-arg factory:

```bash
pyverge doctor --manager myapp.models:UserManager
pyverge doctor --manager myapp.models:create_manager
```

Runtime schemas work when the module exposes a factory that builds the manager
from its runtime source (config file, database, feature flags, etc.). `doctor`
inspects the already-built registry; it does not load schemas itself.

## Commands

| Command | Purpose |
| --- | --- |
| `check` | Validate one payload file against a schema version |
| `validate` | Validate files, directories, or stdin |
| `migrate` | Converge a payload and emit/write the result |
| `diff` | Render a version diff as RFC 6902 |
| `compat` | Check structural compatibility of migrations |
| `doctor` | Validate registry health |
| `export` | Export the registered graph manifest |
| `info` | Show registered models |
| `managers` | List managers in a module |
| `init` | Scaffold models and manager config |

## `doctor`

```bash
pyverge doctor --manager myapp.models:UserManager
pyverge doctor --manager myapp.models:UserManager --format json
```

Checks missing model references and missing adjacent migrations.
Exit `1` when issues are found.

## `validate`

```bash
pyverge validate data.json \
  --manager myapp.models:UserManager \
  --schema User --version 1.0.0

pyverge validate samples/ \
  --manager myapp.models:UserManager \
  --schema User --version 1.0.0 --format json
```

Directories are scanned recursively for `*.json`. Use `--stdin` for a single
payload from standard input. `--fail-fast` stops at the first invalid payload.
Exit `1` when any payload fails.

## `migrate`

```bash
# Print migrated JSON
pyverge migrate data.json --manager myapp.models:UserManager --target latest

# Write output / overwrite input
pyverge migrate data.json --manager myapp.models:UserManager --output out.json
pyverge migrate data.json --manager myapp.models:UserManager --in-place

# CI: converge without writing
pyverge migrate data.json --manager myapp.models:UserManager --check
```

Runtime context:

```bash
pyverge migrate data.json --manager myapp.models:UserManager \
  --context '{"tenant_id": "tenant_99"}'
```

or `--context-file context.json`. `--output` and `--in-place` are mutually
exclusive. Exit `1` when migration fails.

## `compat`

```bash
pyverge compat --manager myapp.models:UserManager
pyverge compat --manager myapp.models:UserManager \
  --schema User --from 1.0.0 --to 2.0.0
pyverge compat --manager myapp.models:UserManager \
  --fail-on-breaking --format json
```

Identity fields (`kind`, `version`) are ignored. Structural breaking changes
are removed fields, type/required changes, and added required fields.
A migration declared backward compatible overrides the structural result.

Exit `0` when compatible, `1` on error, `3` when `--fail-on-breaking` finds a
breaking migration.

## `init`

```bash
pyverge init myproject
pyverge init myproject --pyproject
pyverge init myproject --multiple
```

Creates `models.py` and `pyverge.toml` (or adds `[tool.pyverge]` to
`pyproject.toml`). Config auto-discovery is not implemented yet: commands still
require `--manager module:object_path`.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | Validation, migration, config, or registry failure |
| `2` | Invalid CLI usage |
| `3` | Breaking compatibility with `--fail-on-breaking` |

## CI recipe

```bash
pyverge doctor    --manager myapp.models:UserManager
pyverge validate  samples/ --manager myapp.models:UserManager \
                  --schema User --version 1.0.0
pyverge migrate   samples/current.json --manager myapp.models:UserManager --check
pyverge compat    --manager myapp.models:UserManager --fail-on-breaking
```
