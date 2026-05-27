# Models

## Registration

Register versioned Pydantic models using the `@manager.model()` decorator:

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
```

## Versioning

Versions follow `major.minor.patch` semantic versioning:

- **Major** — breaking changes (removed fields, type changes)
- **Minor** — backward-compatible additions (new optional fields)
- **Patch** — backward-compatible fixes

### Backward Compatible Models

Mark models as backward compatible to skip migration when no changes require data transformation:

```python
@manager.model("Address", "2.0.0", backward_compatible=True)
class AddressV2(AddressV1):
    pass  # No migration needed
```

## Introspection

```python
manager.list_models()          # ["User", "Address"]
manager.list_versions("User")  # [ModelVersion(1,0,0), ModelVersion(2,0,0)]
manager.get_latest("User")     # Latest model class
manager.get("User", "1.0.0")   # Specific version
```
