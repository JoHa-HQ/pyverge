"""Nested versioned models for the CI gate showcase."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class AddressV1(BaseModel):
    kind: Literal["Address"] = "Address"
    version: Literal["1.0.0"] = "1.0.0"
    street: str
    city: str


class AddressV2(BaseModel):
    kind: Literal["Address"] = "Address"
    version: Literal["2.0.0"] = "2.0.0"
    street: str
    city: str
    country: str | None = None


Address = Annotated[AddressV1 | AddressV2, Field(discriminator="version")]


class PersonV1(BaseModel):
    kind: Literal["Person"] = "Person"
    version: Literal["1.0.0"] = "1.0.0"
    name: str
    address: Address


class PersonV2(BaseModel):
    kind: Literal["Person"] = "Person"
    version: Literal["2.0.0"] = "2.0.0"
    name: str
    address: Address
    email: str | None = None
