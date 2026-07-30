"""Provider-specific base for Pydantic test examples.

Import ``BaseModel`` from this module instead of directly from ``pydantic``
so the example models are isolated behind a single provider entry point.
Future model providers can mirror this file with their own base class.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field

__all__ = [
    "AddressBaseModel",
    "BaseModel",
    "ContactBaseModel",
    "Field",
    "PersonBaseModel",
    "UserBaseModel",
]


class BaseModel(PydanticBaseModel):
    """Base class for all Pydantic example models in the test suite."""


class UserBaseModel(BaseModel):
    """Base for ``User`` model family examples."""

    kind: Literal["User"] = "User"


class AddressBaseModel(BaseModel):
    """Base for ``Address`` model family examples."""

    kind: Literal["Address"] = "Address"


class ContactBaseModel(BaseModel):
    """Base for ``Contact`` model family examples."""

    kind: Literal["Contact"] = "Contact"


class PersonBaseModel(BaseModel):
    """Base for ``Person`` model family examples."""

    kind: Literal["Person"] = "Person"
