# CLI

The CLI provides commands for validating, migrating, and exporting schemas without writing Python code.

## Installation

```bash
pip install "pydantic-migrator[cli]"
```

## Configuration

Create a `migrator.toml` in your project:

```toml
[pydantic-migrator]
manager = "models"
```

Or use `[tool.pydantic-migrator]` in `pyproject.toml`.

## Commands

### `init`

Bootstrap a new project with example models and configuration:

```bash
pydantic-migrator init
pydantic-migrator init --pyproject   # Use pyproject.toml
pydantic-migrator init --multiple    # Multiple managers
```

### `info`

List registered models and versions:

```bash
pydantic-migrator info
pydantic-migrator info -c migrator.toml
```

### `validate`

Validate data against a schema version:

```bash
pydantic-migrator validate -d data.json -s User -v 1.0.0
```

### `migrate`

Migrate data between versions:

```bash
pydantic-migrator migrate -d data.json -s User -f 1.0.0 -t 2.0.0
pydantic-migrator migrate -d data.json -s User -f 1.0.0 -t 2.0.0 -o output.json
```

### `diff`

Show differences between schema versions:

```bash
pydantic-migrator diff -s User -f 1.0.0 -t 2.0.0
pydantic-migrator diff -s User -f 1.0.0 -t 2.0.0 --format json
```

### `export`

Export JSON Schema definitions:

```bash
pydantic-migrator export -o ./schemas
```
