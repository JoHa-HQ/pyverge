"""Forward references pattern: break circular dependencies with string type hints.

Useful when:
- The container type references versions not yet defined
- Breaking circular imports between modules
- Cleaner separation of concerns
- Isolated registries per instance (good for tests)
- Dynamic registration at runtime

The manager is initialized with a forward reference BEFORE the container
type is defined — the string is resolved when navigation occurs.
"""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from pydantic_migrator import ModelManager

discriminator = "model_version"
eager_manager = ModelManager["UserContainer"](version_property=discriminator)


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


@eager_manager.model("0.1.1")
class UserV011(BaseModel):
    """Initial user model."""

    name: str
    email: str
    role: Role
    model_version: str = "0.1.1"


@eager_manager.model("0.1.1.dev7")
class UserV011Dev7(BaseModel):
    """Added address and age."""

    name: str
    email: str
    age: int | None = None
    role: Role
    model_version: str = "0.1.1.dev7"


@eager_manager.model("0.0.1")
class UserV001(BaseModel):
    """Added status and updated address."""

    name: str
    email: str
    age: int = Field(default=0, ge=0)
    role: Role
    status: Literal["active", "inactive"] = "active"
    model_version: str = "0.0.1"


@eager_manager.model("1.0.0")
class UserV100(BaseModel):
    """First stable release."""

    name: str
    email: str
    role: Role
    model_version: str = "1.0.0"


@eager_manager.model("1.0.1")
class UserV101(BaseModel):
    """Patch release with bug fixes."""

    name: str
    email: str
    role: Role
    last_login: str | None = None
    model_version: str = "1.0.1"


@eager_manager.model("1.1.0")
class UserV110(BaseModel):
    """Minor release with new optional fields."""

    name: str
    email: str
    role: Role
    last_login: str | None = None
    preferences: dict[str, str] = Field(default_factory=dict)
    model_version: str = "1.1.0"


@eager_manager.model("2.0.0")
class UserV200(BaseModel):
    """Major release with breaking changes."""

    id: str
    name: str
    email: str
    role: Role
    model_version: str = "2.0.0"


@eager_manager.model("2.0.0-beta.1")
class UserV200Beta1(BaseModel):
    """Beta release for 2.0.0."""

    id: str
    name: str
    email: str
    role: Role
    beta_feature_enabled: bool = False
    model_version: str = "2.0.0-beta.1"


User = Annotated[
    UserV011
    | UserV011Dev7
    | UserV001
    | UserV100
    | UserV101
    | UserV110
    | UserV200
    | UserV200Beta1,
    Field(discriminator=discriminator),
]


class UserContainer(BaseModel):
    user: User
