"""Declarative JSON Patch and JSONata migration variant."""

from __future__ import annotations

from typing import Literal

import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.migrations import JsonataMigration, JsonPatchMigration
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.types import ManagerMigrationKey


class UserV1(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["1.0.0"] = "1.0.0"
    name: str


class UserV2(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["2.0.0"] = "2.0.0"
    name: str
    age: int = 0


class UserV3(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["3.0.0"] = "3.0.0"
    name: str
    age: int = 0
    status: str = "active"


def build_declarative_manager() -> Manager[semver.Version]:
    UserManager = Manager[semver.Version].configure(
        PydanticModelAdapter(
            codec=ModelCodec(
                namespace="",
                version_property="version",
                kind_property="kind",
            )
        )
    )
    for model in (UserV1, UserV2, UserV3):
        UserManager.model(model)
    UserManager.store_migration(
        ManagerMigrationKey("User", "1.0.0", "2.0.0"),
        JsonPatchMigration(
            {
                "from": "1.0.0",
                "to": "2.0.0",
                "ops": [{"op": "add", "path": "/age", "value": 0}],
            }
        ),
    )
    UserManager.store_migration(
        ManagerMigrationKey("User", "2.0.0", "3.0.0"),
        JsonataMigration.from_expression('$merge([$, {"status": "active"}])'),
    )
    return UserManager()
