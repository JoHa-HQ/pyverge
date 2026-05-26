# pydantic-migrator

Schema evolution and migrations for Pydantic models. Version your models, define migrations between versions, validate/migrate data at runtime, and export schemas to Avro, Protobuf, TypeScript, and JSON Schema.

## Installation

```bash
# Core library (model versioning, migrations, schema generation)
pip install pydantic-migrator

# With CLI (validate, migrate, diff, export commands)
pip install "pydantic-migrator[cli]"

# With dev dependencies
pip install "pydantic-migrator[dev]"
```

## Quick Start

```python
from pydantic import BaseModel
from pydantic_migrator import ModelManager, Registry

# Register versioned models
registry = Registry()

@registry.register("User", "1.0.0")
class UserV1(BaseModel):
    name: str

@registry.register("User", "2.0.0")
class UserV2(BaseModel):
    name: str
    email: str

# Create manager and register a migration
manager = ModelManager(registry)

@manager.migration("User", "1.0.0", "2.0.0")
def add_email(data):
    return {**data, "email": f"{data['name']}@example.com"}

# Migrate data
migrated = manager.migrate({"name": "Alice"}, "User", "1.0.0", "2.0.0")
```

## CLI

```bash
# Requires: pip install "pydantic-migrator[cli]"

pydantic-migrator init          # Bootstrap a new project
pydantic-migrator validate      # Validate data against a schema version
pydantic-migrator migrate       # Migrate data between versions
pydantic-migrator diff          # Show differences between versions
pydantic-migrator export        # Export schemas (avro, protobuf, typescript, json-schema)
pydantic-migrator info          # List registered models and versions
```

## Features

- **Versioned model registry** — decorator-based registration with semantic versions
- **Step-wise migrations** — register functions between versions with auto-migration for nested models
- **Batch operations** — streaming batch migrations for large datasets
- **Multi-format schema export** — Avro, Protobuf, TypeScript (interface/type/zod), JSON Schema
- **Model diffing** — breaking change detection, markdown/JSON output
- **Migration hooks** — observability via before/after/error callbacks
- **Migration testing** — input/expected-output test framework with pytest integration
