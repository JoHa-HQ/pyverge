"""Lazy registration pattern: define classes first, register later.

Demonstrates both class-level (preferred) and instance-level registration.
Separates model definition from registration, allowing:
- Models to be defined in one module
- Registration to happen elsewhere (e.g. during app startup)
- Easier testing and mocking
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from pydantic_migrator import ModelManager


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


# Define all versions as standalone classes first
class UserV1(BaseModel):
    """Initial user model."""

    name: str
    email: str
    role: Role


class UserV2(BaseModel):
    """Added age field."""

    name: str
    email: str
    age: int | None = None
    role: Role


class UserV3(BaseModel):
    """Added status field."""

    name: str
    email: str
    age: int = Field(default=0, ge=0)
    role: Role
    status: Literal["active", "inactive"] = "active"


# Discriminated union using the injected version property
User = Annotated[
    UserV1 | UserV2 | UserV3,
    Field(discriminator="version"),
]


class UserContainer(BaseModel):
    document: User


# Define migration functions (can be in a separate module)
def migrate_v1_to_v2(data: dict) -> dict:
    data["age"] = None
    return data


def migrate_v2_to_v3(data: dict) -> dict:
    data["age"] = data.get("age", 0)
    data["status"] = "active"
    return data


# ============================================================================
# PATTERN 1: Class-level registration (preferred)
# ============================================================================

Manager = ModelManager[UserContainer]

# Register versions at class level
Manager.model("1.0.0")(UserV1)
Manager.model("2.0.0")(UserV2)
Manager.model("3.0.0")(UserV3)

# Register migrations at class level
Manager.migration("1.0.0", "2.0.0")(migrate_v1_to_v2)
Manager.migration("2.0.0", "3.0.0")(migrate_v2_to_v3)


# ============================================================================
# PATTERN 2: Instance-level registration (alternative)
# ============================================================================

manager = ModelManager[UserContainer](version_property="version")
manager.model("1.0.0")(UserV1)
manager.model("2.0.0")(UserV2)
manager.model("3.0.0")(UserV3)
manager.migration("1.0.0", "2.0.0")(migrate_v1_to_v2)
manager.migration("2.0.0", "3.0.0")(migrate_v2_to_v3)
