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


__all__ = ["AddressV1", "UserV1", "UserV2"]
