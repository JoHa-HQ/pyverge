"""The assembled app converges and routes each event to both targets."""

from __future__ import annotations

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


async def test_v1_event_reaches_both_targets(app, broker, test_broker) -> None:
    seen: dict[str, dict] = {}

    @broker.subscriber("orders.legacy")
    async def legacy(payload: dict) -> None:
        seen["legacy"] = payload

    @broker.subscriber("orders.current")
    async def current(payload: dict) -> None:
        seen["current"] = payload

    async with test_broker(broker) as br:
        await br.publish(V1, "orders.v1")

    assert seen["legacy"]["version"] == "1.0.0"
    assert "currency" not in seen["legacy"]
    assert seen["current"]["version"] == "2.0.0"
    assert seen["current"]["currency"] == "USD"


async def test_v2_event_keeps_its_currency(app, broker, test_broker) -> None:
    seen: dict[str, dict] = {}

    @broker.subscriber("orders.legacy")
    async def legacy(payload: dict) -> None:
        seen["legacy"] = payload

    @broker.subscriber("orders.current")
    async def current(payload: dict) -> None:
        seen["current"] = payload

    async with test_broker(broker) as br:
        await br.publish(V2, "orders.v2")

    assert "currency" not in seen["legacy"]
    assert seen["current"]["currency"] == "EUR"


async def test_lifespan_reflects_the_registered_graph(app, manager) -> None:
    expected_versions = 2
    async with app.lifespan_context():
        assert len(manager.list_versions("Order")) == expected_versions


async def test_one_handler_consumes_both_channels(app, broker, test_broker) -> None:
    seen: dict[str, list[dict]] = {"legacy": [], "current": []}

    @broker.subscriber("orders.legacy")
    async def legacy(payload: dict) -> None:
        seen["legacy"].append(payload)

    @broker.subscriber("orders.current")
    async def current(payload: dict) -> None:
        seen["current"].append(payload)

    async with test_broker(broker) as br:
        await br.publish(V1, "orders.v1")
        await br.publish(V2, "orders.v2")

    legacy_by_id = {item["order_id"]: item for item in seen["legacy"]}
    current_by_id = {item["order_id"]: item for item in seen["current"]}

    assert set(legacy_by_id) == {"1", "2"}
    assert all(item["version"] == "1.0.0" for item in legacy_by_id.values())
    assert all("currency" not in item for item in legacy_by_id.values())

    assert set(current_by_id) == {"1", "2"}
    assert current_by_id["1"]["version"] == "2.0.0"
    assert current_by_id["1"]["currency"] == "USD"
    assert current_by_id["2"]["version"] == "2.0.0"
    assert current_by_id["2"]["currency"] == "EUR"
