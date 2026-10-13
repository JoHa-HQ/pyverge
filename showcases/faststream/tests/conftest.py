"""End-to-end fixtures for the FastStream showcase.

The app is driven through the public broker surface with FastStream's
``TestKafkaBroker`` — an in-memory broker, no Kafka container. Subscribers are
declared with the pyverge ``subscriber`` decorator, whose convergence decoder
runs in the subscriber pipeline, so a published message at any registered
version reaches the handler at the manager target.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest
from faststream.kafka import KafkaBroker
from faststream_demo.domain import build_manager
from faststream_demo.domain.models import Order

from pyverge.adapters.faststream import Reflector, subscriber

TARGET_LATEST = "latest"


@dataclass
class Received:
    """Captures the payloads a subscriber handler saw."""

    payloads: list[dict[str, Any]] = field(default_factory=list)


@pytest.fixture
def manager():
    return build_manager()


@pytest.fixture
def received() -> Received:
    return Received()


@pytest.fixture
def broker(manager, received: Received) -> KafkaBroker:
    """A broker whose ``orders`` subscriber records the converged payload."""
    broker = KafkaBroker("localhost:9092")

    @subscriber(broker, "orders", manager=manager, target=TARGET_LATEST)
    async def handle(order: Order) -> None:
        received.payloads.append(order.model_dump())

    return broker


@pytest.fixture
def reflector(manager) -> Reflector:
    return Reflector(manager)
