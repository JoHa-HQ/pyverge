"""Nested versioned models: models containing other versioned models.

Demonstrates class-level registration pattern.
Shows how versioned models can reference other versioned models,
with each maintaining its own versioning context and independent manager.

The framework automatically detects and migrates nested versioned models
using the discriminator field — no manual delegation needed.
"""

from typing import Annotated

from pydantic import BaseModel, Field

from pydantic_migrator import ModelManager


class AddressV1(BaseModel):
    street: str
    city: str


class AddressV2(BaseModel):
    street: str
    city: str
    country: str | None = None
    postal_code: str | None = None


Address = Annotated[
    AddressV1 | AddressV2,
    Field(discriminator="version"),
]


class AddressContainer(BaseModel):
    document: Address


def migrate_address_100_200(data: dict) -> dict:
    data["country"] = None
    data["postal_code"] = None
    return data


AddressManager = ModelManager[AddressContainer]
AddressManager.model("1.0.0")(AddressV1)
AddressManager.model("2.0.0")(AddressV2)
AddressManager.migration("1.0.0", "2.0.0")(migrate_address_100_200)


class PersonV1(BaseModel):
    """Person with v1 address."""

    name: str
    address: AddressContainer


class PersonV2(BaseModel):
    """Person with v2 address (includes country)."""

    name: str
    email: str
    address: AddressContainer


Person = Annotated[
    PersonV1 | PersonV2,
    Field(discriminator="version"),
]


class PersonContainer(BaseModel):
    document: Person


def migrate_person_100_200(data: dict) -> dict:
    data["email"] = None
    # Nested address is auto-detected and migrated by the framework
    # using the discriminator field (version) in the address data
    return data


PersonManager = ModelManager[PersonContainer]
PersonManager.model("1.0.0")(PersonV1)
PersonManager.model("2.0.0")(PersonV2)
PersonManager.migration("1.0.0", "2.0.0")(migrate_person_100_200)
