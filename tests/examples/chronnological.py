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

from pendulum import Date
from pydantic import BaseModel, Field

# from pydantic_migrator.migration import MigrationSettings, ModelManager

# ChronoManager = ModelManager[Date, MigrationSettings()]


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


# @ChronoManager.model()
class UserV20250101(BaseModel):
    """Added address and age."""

    name: str
    email: str
    age: int | None = None
    role: Role
    version: Literal["2025-01-01"]


# @ChronoManager.model()
class UserV20250310(BaseModel):
    """Initial user model."""

    name: str
    email: str
    role: Role
    version: Literal["2025-03-10"]


# @ChronoManager.model(backward_compatible=True)
class UserV20251231(BaseModel):
    name: str
    email: str
    role: Role
    last_name: str | None = None
    version: Literal["2025-12-31"]


# @ChronoManager.model()
class UserV20260228(BaseModel):
    """Beta release for 2.0.0."""

    id: str
    name: str
    email: str
    role: Role
    beta_feature_enabled: bool = False
    version: Literal["2026-02-28"]


# @ChronoManager.model()
class UserV20260301_120530300Z(BaseModel):
    name: str
    email: str
    role: Role
    version: Literal["2026-03-01T12:05:30+03:00"]


# Step 3: Create discriminated union
User = Annotated[
    UserV20250101 | UserV20250310 | UserV20251231 | UserV20260228,
    Field(discriminator="version"),
]


class UserContainer(BaseModel):
    document: User


# Step 5: Register migrations at class level
# @ChronoManager.migration(UserV20250101, UserV20250310)
def migrate_v1_to_v2(data: dict) -> dict:
    data["age"] = None
    return data


# @ChronoManager.migration(UserV20251231, UserV20260228)
def migrate_v2_to_v3(data: dict) -> dict:
    data["last_name"] = data.get("last_name")
    data["beta_feature_enabled"] = False
    return data
