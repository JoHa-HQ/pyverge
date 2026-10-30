"""Same kind/version isolated across two namespaces."""

from __future__ import annotations

from typing import Literal

import semver
from pydantic import BaseModel

from pyverge import Manager
from pyverge.schemas import ModelCodec, PydanticModelAdapter


class AccountV1(BaseModel):
    kind: Literal["Account"] = "Account"
    version: Literal["1.0.0"] = "1.0.0"
    name: str


def _manager(namespace: str) -> Manager[semver.Version]:
    AccountManager = Manager[semver.Version].configure(
        PydanticModelAdapter(
            codec=ModelCodec(
                namespace=namespace,
                version_property="version",
                kind_property="kind",
            )
        )
    )
    AccountManager.model(AccountV1)
    return AccountManager()


def build_orders_manager() -> Manager[semver.Version]:
    return _manager("com.acme.orders")


def build_billing_manager() -> Manager[semver.Version]:
    return _manager("com.acme.billing")
