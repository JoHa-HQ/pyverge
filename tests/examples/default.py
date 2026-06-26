"""Class-level registration pattern (preferred).

Demonstrates static schema definition separated from dynamic runtime configuration.
Static registrations (models, migrations) happen at class level without instantiation.
Dynamic configuration (version_property, hooks) happens at runtime via instantiation.

Benefits:
- Clean separation of static schema from runtime config
- No instance needed at import time
- Better for production code where schema is fixed
- Defers instantiation until needed
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from pydantic_migrator.migration import ModelManager
from pydantic_migrator.models import ManagerSettings

DefaultManager = ModelManager["UserContainer", ManagerSettings()]


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


@DefaultManager.model(enable_ref=True)
class UserV1(BaseModel):
    """Initial user model."""

    name: str
    email: str
    role: Role
    version: str = Field(default="1.0.0", frozen=True)


@DefaultManager.model()
class UserV2(BaseModel):
    """Added age field."""

    name: str
    email: str
    age: int | None = None
    role: Role
    version: str = Field(default="2.0.0", frozen=True)


@DefaultManager.model()
class UserV3(BaseModel):
    """Added status field."""

    name: str
    email: str
    age: int = Field(default=0, ge=0)
    role: Role
    status: Literal["active", "inactive"] = "active"
    version: str = Field(default="3.0.0", frozen=True)


# Step 3: Create discriminated union
User = Annotated[
    UserV1 | UserV2 | UserV3,
    Field(discriminator="version"),
]


class UserContainer(BaseModel):
    document: User


# Step 5: Register migrations at class level
@DefaultManager.migration("1.0.0", "2.0.0")
def migrate_v1_to_v2(data: dict) -> dict:
    data["age"] = None
    return data


@DefaultManager.migration("2.0.0", "3.0.0")
def migrate_v2_to_v3(data: dict) -> dict:
    data["age"] = data.get("age", 0)
    data["status"] = "active"
    return data
