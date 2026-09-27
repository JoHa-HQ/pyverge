from typing import Annotated, Literal

from tests.examples.pydantic.base import (
    AddressBaseModel,
    BaseModel,
    ContactBaseModel,
    Field,
    PersonBaseModel,
)


class AddressV1(AddressBaseModel):
    street: str
    city: str
    version: Literal["1.0.0"] = "1.0.0"


class AddressV2(AddressBaseModel):
    street: str
    city: str
    country: str | None = None
    postal_code: str | None = None
    version: Literal["2.0.0"] = "2.0.0"


class AddressV3(AddressBaseModel):
    street: str
    city: str
    country: str | None = None
    postal_code: str | None = None
    region: str | None = None
    version: Literal["3.0.0"] = "3.0.0"


Address = Annotated[
    AddressV1 | AddressV2 | AddressV3,
    Field(discriminator="version"),
]


def migrate_address_100_200(data: dict) -> dict:
    data["country"] = None
    data["postal_code"] = None
    return data


def migrate_address_300_200(data: dict) -> dict:
    data.pop("region", None)
    return data


def promote_address(data: dict) -> dict:
    """AddressV1 -> AddressV3: add the fields the newer version introduced."""
    data.setdefault("country", None)
    data.setdefault("postal_code", None)
    data.setdefault("region", None)
    return data


def demote_address(data: dict) -> dict:
    """AddressV3 -> AddressV1: drop fields the older version does not know."""
    for field in ("country", "postal_code", "region"):
        data.pop(field, None)
    return data


class ContactV1(ContactBaseModel):
    phone: str
    version: Literal["1.0.0"] = "1.0.0"


class ContactV2(ContactBaseModel):
    phone: str
    email: str | None = None
    preferred: Literal["phone", "email"] = "phone"
    version: Literal["2.0.0"] = "2.0.0"


Contact = Annotated[
    ContactV1 | ContactV2,
    Field(discriminator="version"),
]


def migrate_contact_100_200(data: dict) -> dict:
    data["email"] = None
    data["preferred"] = "phone"
    return data


class PersonV1(PersonBaseModel):
    name: str
    address: Address
    version: Literal["1.0.0"] = "1.0.0"


class PersonV2(PersonBaseModel):
    name: str
    email: str | None = None
    address: Address
    contacts: list[Contact] = Field(default_factory=list)
    version: Literal["2.0.0"] = "2.0.0"


Person = Annotated[
    PersonV1 | PersonV2,
    Field(discriminator="version"),
]


class PersonContainer(BaseModel):
    document: Person


def migrate_person_100_200(data: dict) -> dict:
    data["email"] = None
    data["contacts"] = []
    return data


def preserve_children_person(data: dict) -> dict:
    """PersonV1 -> PersonV2 migration that keeps already-migrated child data."""
    data.setdefault("email", None)
    data.setdefault("contacts", [])
    return data


def demote_person(data: dict) -> dict:
    """PersonV2 -> PersonV1: drop fields the older version does not know."""
    for field in ("email", "contacts"):
        data.pop(field, None)
    return data
