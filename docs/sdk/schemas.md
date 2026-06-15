# Schema Export

Generate JSON Schema definitions from your versioned Pydantic models.

## JSON Schema

```python
from pathlib import Path

schemas = manager.get_all_schemas()
# {"User": {"1.0.0": {...}, "2.0.0": {...}}, ...}

# Dump to files
manager.dump_schemas(Path("./schemas"))
```

Get a schema for a specific version:

```python
schema = manager.get_schema("User", "1.0.0")
```

Export with separate definition files for nested models:

```python
manager.dump_schemas(
    Path("./schemas"),
    separate_definitions=True,
    ref_template="{model}_v{version}.json",
)
```

## CLI

```bash
pydantic-migrator export -o ./schemas
```
