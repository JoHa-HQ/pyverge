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

latest = manager.get_latest("User")   # VersionedModel container
user_v1 = manager.get("User", "1.0.0")  # VersionedModel container

latest.cls              # Latest model class
user_v1.load(data)      # Validated model instance
```

## Typed registration

For static type inference, parameterize the manager and use subscript registration:

```python
from typing import Annotated, Union
from pydantic import BaseModel, Field
from pydantic_migrator import ModelManager, VersionedModel

manager: ModelManager["UserModel"] = ModelManager()

@manager.register[UserV1]("User", "1.0.0")
class UserV1(BaseModel):
    schema_version: str = "1.0.0"
    name: str

@manager.register[UserV2]("User", "2.0.0")
class UserV2(BaseModel):
    schema_version: str = "2.0.0"
    name: str
    email: str

UserModel = Annotated[
    Union[UserV1, UserV2],
    Field(discriminator="schema_version"),
]

user_v2: VersionedModel[UserModel, UserV2] = manager.get("User", "2.0.0")
instance: UserV2 = user_v2.load({"schema_version": "2.0.0", "name": "Alice", "email": "a@b.com"})
```

## Retrieving models

`get()` and `get_latest()` return a `VersionedModel` container:

```python
versioned = manager.get("User", "2.0.0")

versioned.cls           # Pydantic model class for that version
user = versioned.load(data)  # validated instance
```

Use ``@manager.register[MyModel](...)`` with a parameterized ``ModelManager[T]`` when
you need static type inference for a specific version. The ``@manager.model(...)``
decorator remains available for untyped registration.
