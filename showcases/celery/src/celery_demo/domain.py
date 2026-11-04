"""The version graph for the Celery showcase.

This module is pure domain code: Pydantic models and migration callables. It
does not import Celery or the adapter.
"""

from __future__ import annotations

from typing import Any, Literal

import semver
from pydantic import BaseModel
from pyverge.core.context import MigrationContext

from pyverge import Manager
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


class OrderV3(OrderBase):
    """An order carrying its publication state."""

    version: Literal["3.0.0"] = "3.0.0"
    currency: str = "USD"
    status: Literal["draft", "published"] = "draft"


def add_currency(
    data: dict[str, Any], context: MigrationContext | None = None
) -> dict[str, Any]:
    """v1 -> v2: settlement currency was introduced."""
    return {**data, "currency": "USD"}


def add_status(
    data: dict[str, Any], context: MigrationContext | None = None
) -> dict[str, Any]:
    """v2 -> v3: publication state was introduced."""
    return {**data, "status": "draft"}


def drop_status(
    data: dict[str, Any], context: MigrationContext | None = None
) -> dict[str, Any]:
    """v3 -> v2: discard publication state."""
    data = dict(data)
    data.pop("status", None)
    return data


def drop_currency(
    data: dict[str, Any], context: MigrationContext | None = None
) -> dict[str, Any]:
    """v2 -> v1: discard settlement currency."""
    data = dict(data)
    data.pop("currency", None)
    return data


def build_manager() -> Manager[semver.Version]:
    """Build the fully registered graph. No adapter imports."""
    OrderManager = Manager[semver.Version].configure(
        PydanticModelAdapter(
            codec=ModelCodec(
                namespace="celery.demo",
                version_property="version",
                kind_property="kind",
            )
        ),
        on_missing="reconstruct_model",
    )
    manager = OrderManager()
    for model in (OrderV1, OrderV2, OrderV3):
        manager.store_model(model)
    for source, target, migration in (
        ("1.0.0", "2.0.0", add_currency),
        ("2.0.0", "3.0.0", add_status),
        ("3.0.0", "2.0.0", drop_status),
        ("2.0.0", "1.0.0", drop_currency),
    ):
        manager.store_migration(ManagerMigrationKey("Order", source, target), migration)
    return manager


def order_v1() -> dict[str, Any]:
    """A v1 order payload, as an old producer would publish it."""
    return {
        "kind": "Order",
        "version": "1.0.0",
        "order_id": "ord_101",
        "total": 99.5,
    }


def order_v2() -> dict[str, Any]:
    """The same order at v2."""
    return {**order_v1(), "version": "2.0.0", "currency": "USD"}


def order_v3() -> dict[str, Any]:
    """The same order at v3."""
    return {**order_v2(), "version": "3.0.0", "status": "draft"}


__all__ = [
    "OrderBase",
    "OrderV1",
    "OrderV2",
    "OrderV3",
    "add_currency",
    "add_status",
    "build_manager",
    "drop_currency",
    "drop_status",
    "order_v1",
    "order_v2",
    "order_v3",
]
