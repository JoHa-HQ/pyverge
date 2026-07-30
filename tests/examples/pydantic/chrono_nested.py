"""Date-versioned nested models for graph tests."""

from typing import Annotated, Literal

from tests.examples.pydantic.base import (
    AddressBaseModel,
    BaseModel,
    ContactBaseModel,
    Field,
    PersonBaseModel,
)


class AddressV20240101(AddressBaseModel):
    street: str
    city: str
    version: Literal["2024-01-01"] = "2024-01-01"


class AddressV20240201(AddressBaseModel):
    street: str
    city: str
    country: str | None = None
    version: Literal["2024-02-01"] = "2024-02-01"


Address = Annotated[
    AddressV20240101 | AddressV20240201,
    Field(discriminator="version"),
]


class ContactV20240101(ContactBaseModel):
    phone: str
    version: Literal["2024-01-01"] = "2024-01-01"


class ContactV20240201(ContactBaseModel):
    phone: str
    email: str | None = None
    version: Literal["2024-02-01"] = "2024-02-01"


Contact = Annotated[
    ContactV20240101 | ContactV20240201,
    Field(discriminator="version"),
]


class PersonV20240101(PersonBaseModel):
    name: str
    address: Address
    version: Literal["2024-01-01"] = "2024-01-01"


class PersonV20240201(PersonBaseModel):
    name: str
    address: Address
    contacts: list[Contact] = Field(default_factory=list)
    version: Literal["2024-02-01"] = "2024-02-01"


Person = Annotated[
    PersonV20240101 | PersonV20240201,
    Field(discriminator="version"),
]


class PersonContainer(BaseModel):
    document: Person
