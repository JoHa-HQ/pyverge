# SPDX-FileCopyrightText: Copyright (c) 2026 JoHa-HQ
# SPDX-License-Identifier: GPL-3.0-or-later

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


__all__ = [
    "AddressV1",
    "ContactV1",
    "PersonV1",
    "RequiredValue",
    "UserV1",
    "UserV2",
]
