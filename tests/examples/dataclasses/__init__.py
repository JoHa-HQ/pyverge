"""Dataclass provider examples."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class AddressV1:
    kind: Literal["Address"] = "Address"
    version: Literal["1.0.0"] = "1.0.0"
    street: str = ""


@dataclass
class ContactV1:
    kind: str = "Contact"
    version: str = "1.0.0"
    phone: str = ""


@dataclass
class UserV1:
    kind: Literal["User"] = "User"
    version: Literal["1.0.0"] = "1.0.0"
    name: str = ""
    address: AddressV1 = field(default_factory=AddressV1)


@dataclass
class UserV2:
    kind: Literal["User"] = "User"
    version: Literal["2.0.0"] = "2.0.0"
    name: str = ""
    age: int = 0


@dataclass
class PersonV1:
    kind: str = "Person"
    version: str = "1.0.0"
    name: str = ""
    address: AddressV1 = field(default_factory=AddressV1)
    contacts: list[ContactV1] | None = None


@dataclass
class RequiredValue:
    value: int
    kind: str = field(default="RequiredValue", kw_only=True)
    version: str = field(default="1.0.0", kw_only=True)


@dataclass
class FactoryIdentity:
    kind: str = field(default_factory=lambda: "FactoryIdentity")
    version: str = field(default_factory=lambda: "1.0.0")


@dataclass
class NoKind:
    version: str = "1.0.0"


@dataclass
class BadVersion:
    kind: str = "BadVersion"
    version: str = "nope"


@dataclass
class Node:
    kind: str = "Node"
    version: str = "1.0.0"
    child: Node | None = None


@dataclass
class DuplicateAddresses:
    kind: str = "DuplicateAddresses"
    version: str = "1.0.0"
    first: AddressV1 = field(default_factory=AddressV1)
    second: AddressV1 = field(default_factory=AddressV1)


@dataclass
class WithInitFalse:
    kind: str = "WithInitFalse"
    version: str = "1.0.0"
    value: int = field(default=0, init=False)


@dataclass
class MixedReferences:
    kind: str = "MixedReferences"
    version: str = "1.0.0"
    no_kind: NoKind = field(default_factory=NoKind)
    bad: BadVersion = field(default_factory=BadVersion)
    node: Node = field(default_factory=Node)


__all__ = [
    "AddressV1",
    "BadVersion",
    "ContactV1",
    "DuplicateAddresses",
    "FactoryIdentity",
    "MixedReferences",
    "NoKind",
    "Node",
    "PersonV1",
    "RequiredValue",
    "UserV1",
    "UserV2",
    "WithInitFalse",
]
