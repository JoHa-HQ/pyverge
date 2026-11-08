from typing import Literal

from pydantic import BaseModel


class AddressV2(BaseModel):
    """A delivery address at the anchor version."""

    kind: Literal["Address"] = "Address"
    version: Literal["2.0.0"] = "2.0.0"
    street: str
    city: str
    country: str | None = None


class OrderV3(BaseModel):
    """An order at the anchor version, with its delivery address."""

    kind: Literal["Order"] = "Order"
    version: Literal["3.0.0"] = "3.0.0"
    order_id: str
    amount: float
    currency: str
    address: AddressV2
