"""Static typing checks for discriminated union + VersionedModel narrowing."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from pydantic_migrator import ModelManager, VersionedModel


class UserV0_1_0(BaseModel):
    schema_version: str = "0.1.0"
    name: str


class UserV0_2_0(BaseModel):
    schema_version: str = "0.2.0"
    first_name: str
    last_name: str


UserModel = Annotated[
    UserV0_1_0 | UserV0_2_0,
    Field(discriminator="schema_version"),
]


def typed_registration_flow() -> UserV0_2_0:
    manager: ModelManager[UserModel] = ModelManager[UserModel]()

    @manager.register[UserV0_2_0]("User", "0.2.0")
    class _UserV0_2_0(UserV0_2_0):
        pass

    user_v2: VersionedModel[UserModel, UserV0_2_0] = manager.get("User", "0.2.0")
    latest: VersionedModel[UserModel, UserV0_2_0] = manager.get_latest("User")

    user: UserV0_2_0 = user_v2.load(
        {
            "schema_version": "0.2.0",
            "first_name": "John",
            "last_name": "Doe",
        }
    )
    user_cls: type[UserV0_2_0] = user_v2.cls
    assert user_cls is _UserV0_2_0
    assert latest.cls is _UserV0_2_0
    return user
