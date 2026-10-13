"""Shared fixtures for the FastStream adapter suites.

The version graph comes from the shared ``registry`` fixture in
``tests/conftest.py`` (parametrized indirectly per test). Tests drive the public
broker surface with FastStream's ``TestKafkaBroker`` — an in-memory broker, no
Kafka container.
"""

from __future__ import annotations

from typing import Any

import pytest
from faststream.kafka import KafkaBroker

from pyverge.adapters.faststream import subscriber
from tests.examples.pydantic.semver import UserV2


@pytest.fixture(params=["localhost:9092"], ids=["default"])
def broker_settings(request) -> str:
    """Connection settings for the broker, as fixture params."""
    return request.param


@pytest.fixture
def payloads() -> list[dict[str, Any]]:
    """Collects the payloads a wired subscriber handler saw."""
    return []


@pytest.fixture
def broker(request, broker_settings, manager, payloads) -> KafkaBroker:
    """A broker whose ``users`` subscriber converges through a fresh manager.

    Built from ``broker_settings``; parametrize ``broker`` indirectly with the
    target policy (defaults to ``"latest"``). The handler appends each payload it
    sees to ``payloads``.
    """
    target = getattr(request, "param", "latest")
    instance = manager()
    broker = KafkaBroker(broker_settings)

    @subscriber(broker, "users", manager=instance, target=target)
    async def handle(user: UserV2) -> None:
        payloads.append(user.model_dump())

    return broker
