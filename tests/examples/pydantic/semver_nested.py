"""Nested versioned models — Person with Address and Contacts.

Structure tree::

    PersonContainer
    └── document: Person (discriminator="version")
        ├── PersonV1 (version="1.0.0")
        │   ├── name: str
        │   └── address: Address
        │       ├── AddressV1 (version="1.0.0"): street, city
        │       └── AddressV2 (version="2.0.0"): +country?, +postal_code?
        │
        └── PersonV2 (version="2.0.0")
            ├── name: str
            ├── address: Address   (same discriminated union)
            ├── contacts: list[Contact]
            │   ├── ContactV1 (version="1.0.0"): phone
            │   └── ContactV2 (version="2.0.0"): +email?, +preferred="phone"
            └── AddressV3 (version="3.0.0"): +region?
"""

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
