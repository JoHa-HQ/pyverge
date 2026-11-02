"""The version graph for the httpx showcase.

Pure domain code: Pydantic models and migration callables. The HTTP server and
the httpx transport live outside this module.
"""

from __future__ import annotations

from typing import Any, Literal

import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.core.context import MigrationContext
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.types import ManagerMigrationKey


class OrderBase(BaseModel):
    """Fields shared by every Order version."""

    kind: Literal["Order"] = "Order"
    order_id: str
    total: float


class OrderV1(OrderBase):
    """An order before currency was introduced."""

    version: Literal["1.0.0"] = "1.0.0"


class OrderV2(OrderBase):
    """An order carrying its settlement currency."""

    version: Literal["2.0.0"] = "2.0.0"
    currency: str = "USD"


def add_currency(
    data: dict[str, Any], context: MigrationContext | None = None
) -> dict[str, Any]:
    """v1 -> v2: settlement currency was introduced."""
    return {**data, "currency": "USD"}


def drop_currency(
    data: dict[str, Any], context: MigrationContext | None = None
) -> dict[str, Any]:
    """v2 -> v1: discard settlement currency."""
    data = dict(data)
    data.pop("currency", None)
    return data


def build_manager() -> Manager[semver.Version]:
    """Build the fully registered graph. No httpx imports."""
    OrderManager = Manager[semver.Version].configure(
        PydanticModelAdapter(
            codec=ModelCodec(
                namespace="httpx.demo",
                version_property="version",
                kind_property="kind",
            )
        ),
        on_missing="reconstruct_model",
    )
    manager = OrderManager()
    manager.store_model(OrderV1)
    manager.store_model(OrderV2)
    manager.store_migration(
        ManagerMigrationKey("Order", "1.0.0", "2.0.0"), add_currency
    )
    manager.store_migration(
        ManagerMigrationKey("Order", "2.0.0", "1.0.0"), drop_currency
    )
    return manager


def order_v1() -> dict[str, Any]:
    """A v1 order payload, as an old client would send it."""
    return {
        "kind": "Order",
        "version": "1.0.0",
        "order_id": "ord_101",
        "total": 99.5,
    }


def order_v2() -> dict[str, Any]:
    """The same order at v2."""
    return {**order_v1(), "version": "2.0.0", "currency": "USD"}


__all__ = [
    "OrderBase",
    "OrderV1",
    "OrderV2",
    "add_currency",
    "build_manager",
    "drop_currency",
    "order_v1",
    "order_v2",
]
