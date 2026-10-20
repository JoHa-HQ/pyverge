"""The assembled app converges and routes each event to both targets."""

from __future__ import annotations

from faststream.kafka import TestKafkaBroker

V1 = {
    "specversion": "1.0",
    "id": "1",
    "source": "/orders",
    "type": "Order",
    "data": {"kind": "Order", "version": "1.0.0", "order_id": "1", "total": 9.9},
}
V2 = {
    "specversion": "1.0",
    "id": "2",
    "source": "/orders",
    "type": "Order",
    "data": {
        "kind": "Order",
        "version": "2.0.0",
        "order_id": "2",
        "total": 1.0,
        "currency": "EUR",
    },
}


async def test_v1_event_reaches_both_targets(app, broker) -> None:
    seen: dict[str, dict] = {}

    @broker.subscriber("orders.legacy")
    async def legacy(payload: dict) -> None:
        seen["legacy"] = payload

    @broker.subscriber("orders.current")
    async def current(payload: dict) -> None:
        seen["current"] = payload

    async with TestKafkaBroker(broker) as br:
        await br.publish(V1, "orders.v1")

    assert seen["legacy"]["version"] == "1.0.0"
    assert "currency" not in seen["legacy"]
    assert seen["current"]["version"] == "2.0.0"
    assert seen["current"]["currency"] == "USD"


async def test_v2_event_keeps_its_currency(app, broker) -> None:
    seen: dict[str, dict] = {}

    @broker.subscriber("orders.legacy")
    async def legacy(payload: dict) -> None:
        seen["legacy"] = payload

    @broker.subscriber("orders.current")
    async def current(payload: dict) -> None:
        seen["current"] = payload

    async with TestKafkaBroker(broker) as br:
        await br.publish(V2, "orders.v2")

    assert "currency" not in seen["legacy"]
    assert seen["current"]["currency"] == "EUR"


async def test_lifespan_reflects_the_registered_graph(app, manager) -> None:
    async with app.lifespan_context():
        assert len(manager.list_versions("Order")) == 2
