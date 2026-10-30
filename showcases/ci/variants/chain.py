"""Multi-hop chain with forward and reverse migrations."""

from __future__ import annotations

from typing import Literal

import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.schemas import ModelCodec, PydanticModelAdapter
from pyverge.types import ManagerMigrationKey


class ItemV1(BaseModel):
    kind: Literal["Item"] = "Item"
    version: Literal["1.0.0"] = "1.0.0"
    name: str


class ItemV2(BaseModel):
    kind: Literal["Item"] = "Item"
    version: Literal["2.0.0"] = "2.0.0"
    name: str
    price: int = 0


class ItemV3(BaseModel):
    kind: Literal["Item"] = "Item"
    version: Literal["3.0.0"] = "3.0.0"
    name: str
    price: int = 0
    currency: str = "EUR"


def add_price(data: dict, context=None) -> dict:
    return {**data, "price": 0}


def add_currency(data: dict, context=None) -> dict:
    return {**data, "currency": "EUR"}


def drop_currency(data: dict, context=None) -> dict:
    data = dict(data)
    data.pop("currency", None)
    return data


def drop_price(data: dict, context=None) -> dict:
    data = dict(data)
    data.pop("price", None)
    return data


def build_chain_manager() -> Manager[semver.Version]:
    ItemManager = Manager[semver.Version].configure(
        PydanticModelAdapter(
            codec=ModelCodec(
                namespace="",
                version_property="version",
                kind_property="kind",
            )
        )
    )
    for model in (ItemV1, ItemV2, ItemV3):
        ItemManager.model(model)
    for source, target, func in (
        ("1.0.0", "2.0.0", add_price),
        ("2.0.0", "3.0.0", add_currency),
        ("3.0.0", "2.0.0", drop_currency),
        ("2.0.0", "1.0.0", drop_price),
    ):
        ItemManager.store_migration(ManagerMigrationKey("Item", source, target), func)
    return ItemManager()
