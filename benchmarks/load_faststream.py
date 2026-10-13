"""Sustained FastStream adapter load over the in-memory broker.

Not a pytest-benchmark suite: this is a load loop for throughput
(messages/second) and end-to-end latency, keeping one broker hot.

    uv run python -m benchmarks.load_faststream
"""

from __future__ import annotations

import asyncio
import time

from faststream.kafka import KafkaBroker, TestKafkaBroker

from benchmarks.graphs import user_manager
from benchmarks.synthesis import payloads
from pyverge.adapters.faststream import subscriber
from tests.examples.pydantic.semver import UserV2

TOPIC = "bench"


async def load(messages: int = 20_000) -> None:
    manager = user_manager()
    payload = payloads(manager, "User", "1.0.0", count=1)[0]
    broker = KafkaBroker("localhost:9092")
    handled = 0

    @subscriber(broker, TOPIC, manager=manager, target="latest")
    async def handle(user: UserV2) -> None:
        nonlocal handled
        handled += 1

    async with TestKafkaBroker(broker) as br:
        start = time.perf_counter()
        for _ in range(messages):
            await br.publish(payload, TOPIC)
        elapsed = time.perf_counter() - start

    rate = messages / elapsed
    print(
        f"{rate:,.0f} msg/s  {elapsed / messages * 1e6:.1f} µs/msg  handled={handled}"
    )


if __name__ == "__main__":
    asyncio.run(load())
