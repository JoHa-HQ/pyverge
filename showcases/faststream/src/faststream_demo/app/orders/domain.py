from __future__ import annotations

from typing import Literal, TypedDict, cast

import semver
from pydantic import BaseModel, Field

from pyverge import Manager
from pyverge.migration import MigrationSettings, PydanticModelAdapter


class OrderData(TypedDict):
    """Fields shared by every Order version."""

    kind: Literal["Order"]
    order_id: str
    total: float


class OrderV1Data(OrderData):
    """Order payload at v1 (no currency)."""

    version: Literal["1.0.0"]


class OrderV2Data(OrderData):
    """Order payload at v2 (currency added)."""

    version: Literal["2.0.0"]
    currency: str


class Order(BaseModel):
    """An order event at the anchor version (v2)."""

    kind: Literal["Order"] = "Order"
    version: Literal["2.0.0"] = "2.0.0"
    order_id: str
    total: float = Field(default=0.0)
    currency: str = "USD"


def add_currency(data: OrderV1Data) -> OrderV2Data:
    """v1 -> v2: the event began carrying a currency."""
    data = dict(data)  # ty: ignore[invalid-assignment]
    data["currency"] = "USD"  # ty: ignore[invalid-key]
    return cast(OrderV2Data, data)


def drop_currency(data: OrderV2Data) -> OrderV1Data:
    """v2 -> v1: discard currency for a consumer pinned to the older schema."""
    data = dict(data)  # ty: ignore[invalid-assignment]
    del data["currency"]  # ty: ignore[invalid-argument-type]
    return cast(OrderV1Data, data)


def configure_manager(
    settings: MigrationSettings,
) -> type[Manager[semver.Version]]:
    """Return the configured manager class; assembly instantiates it."""
    return Manager[semver.Version].configure(
        settings,
        PydanticModelAdapter(
            version_property=settings.version_property,
            kind_property=settings.kind_property,
        ),
    )


__all__ = [
    "Order",
    "OrderData",
    "OrderV1Data",
    "OrderV2Data",
    "add_currency",
    "configure_manager",
    "drop_currency",
]
