"""Minimal manager for the CI gate showcase."""

from __future__ import annotations

from typing import Literal

import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.migration import MigrationSettings, PydanticModelAdapter

UserManager = Manager[semver.Version].configure(
    MigrationSettings(),
    PydanticModelAdapter(),
)


@UserManager.model()
class UserV1(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["1.0.0"] = "1.0.0"
    name: str
    email: str


@UserManager.model()
class UserV2(BaseModel):
    kind: Literal["User"] = "User"
    version: Literal["2.0.0"] = "2.0.0"
    name: str
    email: str
    age: int | None = None


@UserManager.migration("User", "1.0.0", "2.0.0")
def add_age(data: dict, context=None) -> dict:
    """v1 -> v2: add the optional age field."""
    return {**data, "age": None}


manager = UserManager()
