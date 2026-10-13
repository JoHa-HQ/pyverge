"""FastStream startup reflection: ``Reflector.reflect`` over a real broker.

``reflect`` is synchronous (subscribers are known at decoration time), so
pytest-benchmark drives it directly.
"""

from __future__ import annotations

from typing import Any

from faststream.kafka import KafkaBroker

from benchmarks.graphs import user_manager
from pyverge.adapters.faststream import Reflector, subscriber
from tests.examples.pydantic.semver import UserV2

TOPIC = "bench"


def test_reflect(benchmark: Any) -> None:
    manager = user_manager()
    broker = KafkaBroker("localhost:9092")

    @subscriber(broker, TOPIC, manager=manager, target="latest")
    async def handle(user: UserV2) -> None: ...

    reflector = Reflector(manager)
    benchmark(lambda: reflector.reflect(broker))
