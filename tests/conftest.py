from __future__ import annotations

from enum import StrEnum
from typing import Literal

import pytest
from pydantic import BaseModel, Field

from pydantic_migrator import ModelManager


class Role(StrEnum):
    ADMIN = "admin"
    USER = "user"
    GUEST = "guest"


class AddressV1(BaseModel):
    street: str
    city: str


class UserV1(BaseModel):
    """Initial user model."""

    name: str
    email: str
    role: Role


class AddressV2(BaseModel):
    """Address with optional country."""

    street: str
    city: str
    country: str | None = None


class UserV2(BaseModel):
    """Added address and age."""

    name: str
    email: str
    age: int | None = None
    role: Role
    address: AddressV1


class AddressV3(BaseModel):
    """Address with zip code."""

    street: str
    city: str
    country: str | None = None
    zip_code: str | None = None


class UserV3(BaseModel):
    """Added status and updated address."""

    name: str
    email: str
    age: int = Field(default=0, ge=0)
    role: Role
    status: Literal["active", "inactive"] = "active"
    address: AddressV3


@pytest.fixture
def manager() -> ModelManager:
    mgr = ModelManager()

    @mgr.model("Address", "1.0.0", backward_compatible=True)
    class _AddrV1(AddressV1):
        pass

    @mgr.model("Address", "2.0.0", backward_compatible=True)
    class _AddrV2(AddressV2):
        pass

    @mgr.model("Address", "3.0.0")
    class _AddrV3(AddressV3):
        pass

    @mgr.model("User", "1.0.0")
    class _UserV1(UserV1):
        pass

    @mgr.model("User", "2.0.0")
    class _UserV2(UserV2):
        pass

    @mgr.model("User", "3.0.0")
    class _UserV3(UserV3):
        pass

    @mgr.migration("Address", "2.0.0", "3.0.0")
    def address_add_zip(data):
        return {**data, "zip_code": None}

    @mgr.migration("User", "1.0.0", "2.0.0")
    def user_v1_to_v2(data):
        return {**data, "age": None, "address": {"street": "", "city": ""}}

    @mgr.migration("User", "2.0.0", "3.0.0")
    def user_v2_to_v3(data):
        return {
            **data,
            "age": data.get("age") or 0,
            "status": "active",
            "address": {**data.get("address", {}), "country": None, "zip_code": None},
        }

    return mgr
