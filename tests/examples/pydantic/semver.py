from enum import StrEnum
from typing import Annotated, Literal

from .base import BaseModel, Field, UserBaseModel


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


# @SemverManager.model()
class UserV011Dev7(UserBaseModel):
    """Added address and age."""

    name: str
    email: str
    age: int | None = None
    role: Role
    version: Literal["0.1.1+dev.7"] = "0.1.1+dev.7"


# @SemverManager.model()
class UserV1(UserBaseModel):
    """Initial user model."""

    name: str
    email: str
    role: Role
    version: Literal["1.0.0"] = "1.0.0"


# @SemverManager.model(backward_compatible=True)
class UserV123(UserBaseModel):
    name: str
    email: str
    role: Role
    last_name: str | None = None
    version: Literal["1.2.3"] = "1.2.3"


# @SemverManager.model()
class UserV200Beta1(UserBaseModel):
    """Beta release for 2.0.0."""

    id: str
    name: str
    email: str
    role: Role
    beta_feature_enabled: bool = False
    version: Literal["2.0.0-beta.1"] = "2.0.0-beta.1"


# @SemverManager.model(backward_compatible=True)
class UserV2(UserBaseModel):
    """Added age field."""

    name: str
    email: str
    age: int | None = None
    role: Role
    version: Literal["2.0.0"] = "2.0.0"


# @SemverManager.model()
class UserV3(UserBaseModel):
    """Added status field."""

    name: str
    email: str
    age: int = Field(default=0, ge=0)
    role: Role
    status: Literal["active", "inactive"] = "active"
    version: Literal["3.0.0"] = "3.0.0"


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


class InvalidBetaModel(UserBaseModel):
    """Invalid semver: prerelease without a version number."""

    name: str
    version: Literal["beta.7"] = "beta.7"


class InvalidAlphaModel(UserBaseModel):
    """Invalid semver: too many version segments."""

    name: str
    version: Literal["0.0.0.alpha7"] = "0.0.0.alpha7"


class InvalidTimeModel(UserBaseModel):
    """Invalid date: a time-of-day, not a calendar date."""

    name: str
    version: Literal["15:15:20.000Z"] = "15:15:20.000Z"
