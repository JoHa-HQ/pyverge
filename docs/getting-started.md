# Getting Started

## Installation

```bash
# Core library
pip install pydantic-migrator

# With CLI
pip install "pydantic-migrator[cli]"
```

## Quick Start

```python
from pydantic import BaseModel
from pydantic_migrator import ModelManager

manager = ModelManager()

@manager.model("User", "1.0.0")
class UserV1(BaseModel):
    name: str
    email: str

@manager.model("User", "2.0.0")
class UserV2(BaseModel):
    name: str
    email: str
    age: int | None = None

@manager.migration("User", "1.0.0", "2.0.0")
def add_age(data):
    return {**data, "age": None}

# Migrate data
migrated = manager.migrate(
    {"name": "Alice", "email": "alice@example.com"},
    "User", "1.0.0", "2.0.0"
)
```

## Next Steps

- Learn about [model registration](sdk/models.md)
- Define [migrations](sdk/migrations.md)
- [Export schemas](sdk/schemas.md) as JSON Schema
- Use the [CLI](cli.md) for project bootstrapping
