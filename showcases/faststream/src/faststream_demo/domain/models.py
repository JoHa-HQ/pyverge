"""The anchor model — the newest shape of the versioned kind.

The source of truth for the kind's newest version. The older version is
reconstructed from the anchor by the engine as each migration edge is
registered; it is never declared by hand.

The demo exposes one kind, ``Order``, carried over a FastStream broker:

* ``Order`` — the versioned message whose body is the record.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Order(BaseModel):
    """An order event at the anchor version (v2).

    ``total`` was always present; ``currency`` arrived in v2.
    """

    kind: Literal["Order"] = "Order"
    version: Literal["2.0.0"] = "2.0.0"
    order_id: str
    total: float = Field(default=0.0)
    currency: str = "USD"
