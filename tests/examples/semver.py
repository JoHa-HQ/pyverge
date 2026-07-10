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
from semver import Version

# from pydantic_migrator.migration import MigrationSettings, ModelManager

# SemverManager = ModelManager[Version, MigrationSettings()]


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


# @SemverManager.model()
class UserV011Dev7(BaseModel):
    """Added address and age."""

    name: str
    email: str
    age: int | None = None
    role: Role
    version: Literal["0.1.1+dev.7"]


# @SemverManager.model()
class UserV1(BaseModel):
    """Initial user model."""

    name: str
    email: str
    role: Role
    version: Literal["1.0.0"]


# @SemverManager.model(backward_compatible=True)
class UserV123(BaseModel):
    name: str
    email: str
    role: Role
    last_name: str | None = None
    version: Literal["1.2.3"]


# @SemverManager.model()
class UserV200Beta1(BaseModel):
    """Beta release for 2.0.0."""

    id: str
    name: str
    email: str
    role: Role
    beta_feature_enabled: bool = False
    version: Literal["2.0.0-beta.1"]


# @SemverManager.model(backward_compatible=True)
class UserV2(BaseModel):
    """Added age field."""

    name: str
    email: str
    age: int | None = None
    role: Role
    version: Literal["2.0.0"]


# @SemverManager.model()
class UserV3(BaseModel):
    """Added status field."""

    name: str
    email: str
    age: int = Field(default=0, ge=0)
    role: Role
    status: Literal["active", "inactive"] = "active"
    version: Literal["3.0.0"]


User = Annotated[
    UserV011Dev7 | UserV1 | UserV123 | UserV200Beta1 | UserV2 | UserV3,
    Field(discriminator="version"),
]


class UserContainer(BaseModel):
    document: User


# @SemverManager.migration(UserV1, UserV2)
def migrate_v1_to_v2(data: dict) -> dict:
    data["age"] = None
    return data


# @SemverManager.migration(UserV2, UserV3)
def migrate_v2_to_v3(data: dict) -> dict:
    data["age"] = data.get("age", 0)
    data["status"] = "active"
    return data
