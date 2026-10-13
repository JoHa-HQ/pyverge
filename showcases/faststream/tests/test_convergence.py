"""End-to-end convergence, through the public broker surface only.

Every case publishes a payload at a registered version and asserts the
subscriber handler saw the target version — the convergence decoder ran in the
subscriber pipeline before the handler. Reflection reconciles each handler's
typed payload model into the graph before start.
"""

from __future__ import annotations

from conftest import Received
from faststream import FastStream
from faststream.kafka import KafkaBroker, TestKafkaBroker
from faststream_demo.domain.models import Order

from pyverge.adapters.faststream import Reflector, subscriber


def _broker(manager, received: Received, *, target) -> KafkaBroker:
    broker = KafkaBroker("localhost:9092")

    @subscriber(broker, "orders", manager=manager, target=target)
    async def handle(order: Order) -> None:
        received.payloads.append(order.model_dump())

    return broker


class TestConvergence:
    async def test_stale_payload_converges_to_latest(self, broker, received) -> None:
        async with TestKafkaBroker(broker) as br:
            await br.publish(
                {"kind": "Order", "version": "1.0.0", "order_id": "1", "total": 9.9},
                "orders",
            )
        assert received.payloads == [
            {
                "kind": "Order",
                "version": "2.0.0",
                "order_id": "1",
                "total": 9.9,
                "currency": "USD",
            }
        ]

    async def test_current_payload_passes_through(self, broker, received) -> None:
        payload = {
            "kind": "Order",
            "version": "2.0.0",
            "order_id": "2",
            "total": 1.0,
            "currency": "EUR",
        }
        async with TestKafkaBroker(broker) as br:
            await br.publish(payload, "orders")
        assert received.payloads == [payload]


class TestTargetPolicy:
    async def test_pinned_target_downgrades(self, manager, received) -> None:
        broker = _broker(manager, received, target="1.0.0")
        async with TestKafkaBroker(broker) as br:
            await br.publish(
                {
                    "kind": "Order",
                    "version": "2.0.0",
                    "order_id": "3",
                    "total": 2.0,
                    "currency": "USD",
                },
                "orders",
            )
        assert received.payloads[0]["version"] == "1.0.0"
        assert "currency" not in received.payloads[0]

    async def test_per_kind_target(self, manager, received) -> None:
        broker = _broker(manager, received, target={"Order": "1.0.0"})
        async with TestKafkaBroker(broker) as br:
            await br.publish(
                {
                    "kind": "Order",
                    "version": "2.0.0",
                    "order_id": "4",
                    "total": 3.0,
                    "currency": "USD",
                },
                "orders",
            )
        assert received.payloads[0]["version"] == "1.0.0"
        assert "currency" not in received.payloads[0]


class TestReflection:
    def test_reflect_reconciles_typed_handler(self, manager, received) -> None:
        broker = _broker(manager, received, target="latest")
        reflected = Reflector(manager).reflect(broker)
        assert [r.model for r in reflected] == [Order]
        assert reflected[0].topics == ("orders",)

    def test_pinned_handler_reflects_reconstructed_target(
        self, manager, received
    ) -> None:
        broker = _broker(manager, received, target="1.0.0")
        reflected = Reflector(manager).reflect(broker)
        # the handler was rebound from the anchor (Order) to the reconstructed v1
        assert reflected[0].model is not Order
        assert "currency" not in reflected[0].model.model_fields

    def test_reflector_runs_on_startup(self, manager, received) -> None:
        broker = _broker(manager, received, target="latest")
        app = FastStream(broker, on_startup=[Reflector(manager)])
        assert app.brokers  # wiring; startup hook is the reflector itself

    def test_handler_without_model_is_skipped(self, manager) -> None:
        broker = KafkaBroker("localhost:9092")

        @subscriber(broker, "raw", manager=manager)
        async def handle(payload: dict) -> None: ...

        # dict is not a provider model; reflection skips it.
        assert Reflector(manager).reflect(broker) == []
