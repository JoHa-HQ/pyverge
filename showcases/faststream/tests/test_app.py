from decimal import Decimal
from typing import Any

import pytest
from faststream.kafka import TestKafkaBroker

pytestmark = pytest.mark.xfail(
    reason="Waiting for new FastStream adapter API in pyverge (#167)",
    strict=True,
)


# Case 1: a message in an older version is converged to the handler's version
async def test_older_version_converged_to_handler_version(container, order_v1):
    app = container.app()
    ledger = container.ledger()
    broker = app.broker

    v1_order = order_v1("order-1", total=100.0)

    async with TestKafkaBroker(broker) as br:
        await br.publish(v1_order, "orders", headers={"type": "retail"})

    assert len(ledger.invoices) == 1
    invoice = ledger.invoices[0]
    assert invoice.order_id == "order-1"
    assert invoice.amount == Decimal("100.00")
    assert invoice.currency == "USD"


# Case 2: several handlers on one topic each receive their own version
async def test_several_handlers_on_one_topic_routed_by_filter(container, order_v1):
    app = container.app()
    ledger = container.ledger()
    broker = app.broker

    v1_retail = order_v1("retail-1")
    v1_wholesale = order_v1("wholesale-1")

    async with TestKafkaBroker(broker) as br:
        await br.publish(v1_retail, "orders", headers={"type": "retail"})
        await br.publish(v1_wholesale, "orders", headers={"type": "wholesale"})

    expected_invoices = 2
    assert len(ledger.invoices) == expected_invoices
    invoices_by_id = {inv.order_id: inv for inv in ledger.invoices}
    assert invoices_by_id["retail-1"].currency == "USD"
    assert invoices_by_id["wholesale-1"].currency == "EUR"


# Case 3: retail and wholesale orders migrate along different paths (discriminator)
async def test_retail_and_wholesale_migrate_along_different_paths(container, order_v1):
    app = container.app()
    ledger = container.ledger()
    broker = app.broker

    v1_order = order_v1("discrim-1", total=100.0)

    async with TestKafkaBroker(broker) as br:
        await br.publish(v1_order, "orders", headers={"type": "wholesale"})

    assert len(ledger.invoices) == 1
    invoice = ledger.invoices[0]
    assert invoice.currency == "EUR"
    assert invoice.amount == Decimal("90.00")


# Case 4: a nested object (an address inside an order) is preserved and converged
async def test_nested_address_preserved_and_converged(container, order_v1):
    app = container.app()
    ledger = container.ledger()
    broker = app.broker

    v1_order = order_v1(
        "nested-1",
        total=50.0,
        address={
            "kind": "Address",
            "version": "1.0.0",
            "street": "Baker Street",
            "city": "London",
        },
    )

    async with TestKafkaBroker(broker) as br:
        await br.publish(v1_order, "orders", headers={"type": "retail"})

    assert len(ledger.invoices) == 1
    invoice = ledger.invoices[0]
    assert invoice.shipping_country is None


# Case 5: a handler without a model receives the message unchanged
async def test_handler_without_model_receives_message_unchanged(container):
    app = container.app()
    ledger = container.ledger()
    audit = container.audit()
    broker = app.broker

    raw_message = {"event": "ping", "timestamp": 1234567890}

    async with TestKafkaBroker(broker) as br:
        await br.publish(raw_message, "orders", headers={"type": "unknown"})

    assert len(ledger.invoices) == 0
    assert len(audit.entries) == 1
    assert audit.entries[0] == raw_message


# Case 6: a message that cannot be converged is not passed to the handler
async def test_unconvergeable_message_is_not_passed_to_handler(container, order_v1):
    app = container.app()
    ledger = container.ledger()
    broker = app.broker

    unsupported_order = order_v1("bad-99", version="99.0.0")

    async with TestKafkaBroker(broker) as br:
        await br.publish(unsupported_order, "orders", headers={"type": "retail"})

    assert len(ledger.invoices) == 0


# Case 7: the result is published to different consumers in different versions
async def test_result_published_to_different_consumers_in_different_versions(
    container, order_v1
):
    app = container.app()
    broker = app.broker

    expected_amount = 100.0
    v1_order = order_v1("fanout-1", total=expected_amount)

    seen: dict[str, dict[str, Any]] = {}

    @broker.subscriber("orders.legacy")
    async def on_legacy(msg: dict[str, Any]) -> None:
        seen["legacy"] = msg

    @broker.subscriber("orders.current")
    async def on_current(msg: dict[str, Any]) -> None:
        seen["current"] = msg

    async with TestKafkaBroker(broker) as br:
        await br.publish(v1_order, "orders", headers={"type": "retail"})

    assert seen["legacy"]["version"] == "1.0.0"
    assert "currency" not in seen["legacy"]
    assert seen["current"]["version"] == "3.0.0"
    assert seen["current"]["amount"] == expected_amount
    assert seen["current"]["currency"] == "USD"


# Case 8: the result version is selected from the consumer's header
async def test_result_version_selected_from_consumer_header(container, order_v1):
    app = container.app()
    broker = app.broker

    expected_total = 75.0
    v1_request = order_v1(
        "req-1",
        total=expected_total,
        address={
            "kind": "Address",
            "version": "1.0.0",
            "street": "Via Roma",
            "city": "Rome",
        },
    )

    seen_replies: list[dict[str, Any]] = []

    @broker.subscriber("orders.replies")
    async def on_reply(msg: dict[str, Any]) -> None:
        seen_replies.append(msg)

    async with TestKafkaBroker(broker) as br:
        await br.publish(
            v1_request,
            "orders.requests",
            headers={"accept-version": "1.0.0"},
        )

    assert len(seen_replies) == 1
    assert seen_replies[0]["version"] == "1.0.0"
