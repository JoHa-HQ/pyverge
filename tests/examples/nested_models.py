"""Nested versioned models — Person with Address and Contacts.

Structure tree::

    PersonContainer
    └── document: Person (discriminator="v")
        ├── PersonV1 (v="1.0.0")
        │   ├── name: str
        │   └── address: Address
        │       ├── AddressV1 (v="1.0.0"): street, city
        │       └── AddressV2 (v="2.0.0"): +country?, +postal_code?
        │
        └── PersonV2 (v="2.0.0")
            ├── name: str
            ├── address: Address   (same discriminated union)
            ├── contacts: list[Contact]
            │   ├── ContactV1 (v="1.0.0"): phone
            │   └── ContactV2 (v="2.0.0"): +email?, +preferred="phone"
            └── AddressV3 (v="3.0.0"): +region?  (backward → v2 via migrate_address_300_200)
"""  # noqa: E501

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from pydantic_migrator.migration import MigrationSettings, ModelManager

version_predicate = "v"
NestedModelManager = ModelManager[
    "PersonContainer", MigrationSettings(version_property=version_predicate)
]


@NestedModelManager.model()
class AddressV1(BaseModel):
    street: str
    city: str
    v: Literal["1.0.0"]


@NestedModelManager.model(backward_compatible=True)
class AddressV2(BaseModel):
    street: str
    city: str
    country: str | None = None
    postal_code: str | None = None
    v: Literal["2.0.0"]


@NestedModelManager.migration("1.0.0", "2.0.0")
def migrate_address_100_200(data: dict) -> dict:
    data["country"] = None
    data["postal_code"] = None
    return data


@NestedModelManager.model()
class AddressV3(BaseModel):
    street: str
    city: str
    country: str | None = None
    postal_code: str | None = None
    region: str | None = None
    v: Literal["3.0.0"]


Address = Annotated[
    AddressV1 | AddressV2 | AddressV3,
    Field(discriminator=version_predicate),
]


@NestedModelManager.migration("3.0.0", "2.0.0")
def migrate_address_300_200(data: dict) -> dict:
    data.pop("region", None)
    return data


@NestedModelManager.model()
class ContactV1(BaseModel):
    phone: str
    v: Literal["1.0.0"]


@NestedModelManager.model()
class ContactV2(BaseModel):
    phone: str
    email: str | None = None
    preferred: Literal["phone", "email"] = "phone"
    v: Literal["2.0.0"]


Contact = Annotated[
    ContactV1 | ContactV2,
    Field(discriminator=version_predicate),
]


@NestedModelManager.migration("1.0.0", "2.0.0")
def migrate_contact_100_200(data: dict) -> dict:
    data["email"] = None
    data["preferred"] = "phone"
    return data


@NestedModelManager.model()
class PersonV1(BaseModel):
    name: str
    address: Address
    v: Literal["1.0.0"]


@NestedModelManager.model()
class PersonV2(BaseModel):
    name: str
    email: str
    address: Address
    contacts: list[Contact] = []
    v: Literal["2.0.0"]


Person = Annotated[
    PersonV1 | PersonV2,
    Field(discriminator=version_predicate),
]


class PersonContainer(BaseModel):
    document: Person


@NestedModelManager.migration("1.0.0", "2.0.0")
def migrate_person_100_200(data: dict) -> dict:
    data["email"] = None
    data["contacts"] = []
    return data
