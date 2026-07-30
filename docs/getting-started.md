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

## Registration Patterns

### Lazy registration

Define model classes first and register them later, either at the class level or on a manager instance. This keeps schema definition separate from runtime wiring and makes testing easier.

```python
from pydantic import BaseModel
from pydantic_migrator import ModelManager

class UserV1(BaseModel):
    name: str
    email: str

class UserV2(BaseModel):
    name: str
    email: str
    age: int | None = None

def add_age(data: dict) -> dict:
    data["age"] = None
    return data

# Class-level registration (preferred)
Manager = ModelManager
Manager.model("User", "1.0.0")(UserV1)
Manager.model("User", "2.0.0")(UserV2)
Manager.migration("User", "1.0.0", "2.0.0")(add_age)

# Instance-level registration (alternative)
manager = ModelManager()
manager.model("User", "1.0.0")(UserV1)
manager.model("User", "2.0.0")(UserV2)
manager.migration("User", "1.0.0", "2.0.0")(add_age)
```

## Next Steps

- Learn about [model registration](sdk/models.md)
- Define [migrations](sdk/migrations.md)
- [Export schemas](sdk/schemas.md) as JSON Schema
- Use the [CLI](cli.md) for project bootstrapping
